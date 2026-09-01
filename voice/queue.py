import asyncio
from dataclasses import dataclass

import discord

from voice.manager import VoiceManager


@dataclass(frozen=True)
class TTSQueueItem:
    nomor: int
    text: str


class TTSQueue:
    def __init__(self, manager: VoiceManager, voice_client: discord.VoiceClient) -> None:
        self.manager: VoiceManager = manager
        self.voice_client: discord.VoiceClient = voice_client
        self.items: asyncio.Queue[TTSQueueItem | None] = asyncio.Queue()
        self.worker: asyncio.Task[None] | None = None
        self.next_number: int = 1
        self.error: Exception | None = None

    def start(self) -> None:
        if self.worker is not None:
            raise RuntimeError("Worker TTS queue sudah berjalan.")
        self.worker = asyncio.create_task(self._run())

    async def enqueue(self, text: str) -> int:
        self.raise_worker_error()
        if self.worker is None:
            raise RuntimeError("Worker TTS queue belum dijalankan.")
        if not text.strip():
            raise ValueError("Teks TTS queue tidak boleh kosong.")

        item: TTSQueueItem = TTSQueueItem(nomor=self.next_number, text=text)
        self.next_number += 1
        await self.items.put(item)
        return self.items.qsize()

    async def finish(self) -> None:
        if self.worker is None:
            raise RuntimeError("Worker TTS queue belum dijalankan.")
        if not self.worker.done():
            await self.items.join()
            await self.items.put(None)
        await self.worker
        self.raise_worker_error()

    def raise_worker_error(self) -> None:
        if self.error is not None:
            raise RuntimeError(f"TTS queue gagal memproses audio: {self.error}") from self.error

    async def _run(self) -> None:
        try:
            while True:
                item: TTSQueueItem | None = await self.items.get()
                if item is None:
                    self.items.task_done()
                    return
                try:
                    print(f"\nVOICE [{item.nomor}] > mulai berbicara")
                    await self.manager.speak(self.voice_client, item.text)
                    print(f"VOICE [{item.nomor}] > selesai")
                    print("TTS > ", end="", flush=True)
                finally:
                    self.items.task_done()
        except Exception as error:
            self.error = error
            while not self.items.empty():
                self.items.get_nowait()
                self.items.task_done()
