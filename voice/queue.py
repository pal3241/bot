import asyncio
import time
from dataclasses import dataclass

import discord

from config import TTS_READY_QUEUE_SIZE
from voice.manager import PreparedAudio, VoiceManager


@dataclass(frozen=True)
class TTSQueueItem:
    nomor: int
    text: str
    enqueued_at: float


@dataclass(frozen=True)
class ReadyQueueItem:
    request: TTSQueueItem
    prepared: PreparedAudio


class TTSQueue:
    def __init__(self, manager: VoiceManager, voice_client: discord.VoiceClient) -> None:
        self.manager: VoiceManager = manager
        self.voice_client: discord.VoiceClient = voice_client
        self.text_queue: asyncio.Queue[TTSQueueItem | None] = asyncio.Queue()
        self.ready_queue: asyncio.Queue[ReadyQueueItem | None] = asyncio.Queue(
            maxsize=TTS_READY_QUEUE_SIZE
        )
        self.preparation_worker: asyncio.Task[None] | None = None
        self.playback_worker: asyncio.Task[None] | None = None
        self.next_number: int = 1
        self.fatal_error: Exception | None = None
        self.closing: bool = False

    @property
    def is_running(self) -> bool:
        return (
            self.preparation_worker is not None
            and self.playback_worker is not None
            and not self.preparation_worker.done()
            and not self.playback_worker.done()
        )

    @property
    def is_finished(self) -> bool:
        return (
            self.preparation_worker is not None
            and self.playback_worker is not None
            and self.preparation_worker.done()
            and self.playback_worker.done()
        )

    def start(self) -> None:
        if self.preparation_worker is not None or self.playback_worker is not None:
            raise RuntimeError("Worker TTS queue sudah pernah dijalankan.")
        self.preparation_worker = asyncio.create_task(self._prepare())
        self.playback_worker = asyncio.create_task(self._play())

    async def enqueue(self, text: str) -> int:
        self.raise_worker_error()
        if not self.is_running or self.closing:
            raise RuntimeError("TTS queue tidak menerima item baru.")
        if not text.strip():
            raise ValueError("Teks TTS queue tidak boleh kosong.")
        item: TTSQueueItem = TTSQueueItem(
            nomor=self.next_number,
            text=text,
            enqueued_at=time.perf_counter(),
        )
        self.next_number += 1
        await self.text_queue.put(item)
        return self.text_queue.qsize()

    async def finish(self) -> None:
        if self.preparation_worker is None or self.playback_worker is None:
            raise RuntimeError("Worker TTS queue belum dijalankan.")
        if self.fatal_error is not None:
            await self.abort()
            self.raise_worker_error()
        if not self.closing:
            self.closing = True
            await self.text_queue.put(None)
        await asyncio.gather(self.preparation_worker, self.playback_worker)
        self.raise_worker_error()

    async def abort(self) -> None:
        self.closing = True
        workers: list[asyncio.Task[None]] = [
            worker
            for worker in (self.preparation_worker, self.playback_worker)
            if worker is not None and not worker.done()
        ]
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        if self.voice_client.is_playing():
            self.voice_client.stop()
        self._clear_text_queue()
        await self._clear_ready_queue()

    def raise_worker_error(self) -> None:
        if self.fatal_error is not None:
            raise RuntimeError(
                f"Worker TTS queue berhenti: {self.fatal_error}"
            ) from self.fatal_error

    async def clear_pending(self) -> int:
        removed: int = 0
        while not self.text_queue.empty():
            item: TTSQueueItem | None = self.text_queue.get_nowait()
            self.text_queue.task_done()
            if item is not None:
                removed += 1
        while not self.ready_queue.empty():
            ready: ReadyQueueItem | None = self.ready_queue.get_nowait()
            self.ready_queue.task_done()
            if ready is not None:
                await self.manager.cleanup_prepared(ready.prepared)
                removed += 1
        return removed

    @property
    def pending_count(self) -> int:
        return self.text_queue.qsize() + self.ready_queue.qsize()

    async def _prepare(self) -> None:
        try:
            while True:
                request: TTSQueueItem | None = await self.text_queue.get()
                if request is None:
                    self.text_queue.task_done()
                    await self.ready_queue.put(None)
                    return
                prepared: PreparedAudio | None = None
                try:
                    print(f"\nVOICE [{request.nomor}] > menyiapkan audio")
                    prepared = await self.manager.prepare(request.text)
                    await self.ready_queue.put(ReadyQueueItem(request, prepared))
                    prepared = None
                    elapsed: float = time.perf_counter() - request.enqueued_at
                    print(f"VOICE [{request.nomor}] > siap ({elapsed:.3f}s sejak enqueue)")
                except asyncio.CancelledError:
                    if prepared is not None:
                        await self.manager.cleanup_prepared(prepared)
                    raise
                except Exception as error:
                    print(
                        f"VOICE [{request.nomor}] > GAGAL PREPARE: "
                        f"{type(error).__name__}: {error}"
                    )
                finally:
                    self.text_queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.fatal_error = error
            await self.ready_queue.put(None)

    async def _play(self) -> None:
        try:
            while True:
                item: ReadyQueueItem | None = await self.ready_queue.get()
                if item is None:
                    self.ready_queue.task_done()
                    return
                try:
                    print(f"\nVOICE [{item.request.nomor}] > mulai berbicara")
                    await self.manager.play_prepared(self.voice_client, item.prepared)
                    print(f"VOICE [{item.request.nomor}] > selesai")
                    print("TTS > ", end="", flush=True)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    print(
                        f"VOICE [{item.request.nomor}] > GAGAL PLAYBACK: "
                        f"{type(error).__name__}: {error}"
                    )
                finally:
                    await self.manager.cleanup_prepared(item.prepared)
                    self.ready_queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.fatal_error = error

    def _clear_text_queue(self) -> None:
        while not self.text_queue.empty():
            self.text_queue.get_nowait()
            self.text_queue.task_done()

    async def _clear_ready_queue(self) -> None:
        while not self.ready_queue.empty():
            item: ReadyQueueItem | None = self.ready_queue.get_nowait()
            if item is not None:
                await self.manager.cleanup_prepared(item.prepared)
            self.ready_queue.task_done()
