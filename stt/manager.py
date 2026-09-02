import asyncio
from collections.abc import Awaitable, Callable

from stt.models import AudioUtterance, STTResult
from stt.providers import FasterWhisperProvider
from stt.providers.base import STTProvider
from stt.settings import STTSettings


ResultHandler = Callable[[STTResult], Awaitable[None]]


class STTManager:
    def __init__(self, settings: STTSettings, result_handler: ResultHandler) -> None:
        self.settings: STTSettings = settings
        self._result_handler: ResultHandler = result_handler
        self._provider: STTProvider = self._create_provider(settings)
        self._queue: asyncio.Queue[AudioUtterance | None] = asyncio.Queue(
            maxsize=settings.queue_size
        )
        self._workers: list[asyncio.Task[None]] = []
        self._last_error: Exception | None = None

    @staticmethod
    def _create_provider(settings: STTSettings) -> STTProvider:
        if settings.provider == "faster_whisper":
            return FasterWhisperProvider(settings.model)
        raise ValueError(f"Provider STT tidak tersedia: '{settings.provider}'.")

    def start(self) -> None:
        if self._workers:
            raise RuntimeError("STT Manager sudah berjalan.")
        self._workers = [
            asyncio.create_task(self._worker(number), name=f"stt-worker-{number}")
            for number in range(1, self.settings.workers + 1)
        ]

    def submit(self, utterance: AudioUtterance) -> None:
        self.raise_worker_error()
        try:
            self._queue.put_nowait(utterance)
        except asyncio.QueueFull as error:
            raise RuntimeError(
                f"STT queue penuh: size={self.settings.queue_size}, "
                f"user={utterance.user_id}, duration={utterance.duration_seconds:.3f}s"
            ) from error
        if self.settings.log_transcript:
            print(
                f"[STT] speech queued user={utterance.user_id} "
                f"duration={utterance.duration_seconds:.3f}s queue={self._queue.qsize()}"
            )

    async def _worker(self, number: int) -> None:
        try:
            while True:
                utterance: AudioUtterance | None = await self._queue.get()
                if utterance is None:
                    self._queue.task_done()
                    return
                try:
                    result: STTResult = await self._provider.transcribe(
                        utterance, self.settings.language
                    )
                    if self.settings.log_transcript:
                        print(
                            f"[STT] transcript worker={number} user={result.user_id} "
                            f"language={result.language} latency={result.latency_seconds:.3f}s "
                            f"text={result.text!r}"
                        )
                    await self._result_handler(result)
                except Exception as error:
                    print(
                        f"[STT] utterance failed worker={number} "
                        f"type={type(error).__name__} detail={error}"
                    )
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._last_error = error

    def raise_worker_error(self) -> None:
        if self._last_error is not None:
            raise RuntimeError(f"STT worker berhenti: {self._last_error}") from self._last_error

    async def close(self) -> None:
        workers: list[asyncio.Task[None]] = [
            worker for worker in self._workers if not worker.done()
        ]
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        self._workers.clear()
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()
        await self._provider.close()

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()
