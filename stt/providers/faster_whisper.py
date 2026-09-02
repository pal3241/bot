import asyncio
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from faster_whisper import WhisperModel
from faster_whisper.transcribe import Segment, TranscriptionInfo

from stt.audio.processor import pcm_stereo_48k_to_mono_16k
from stt.models import AudioUtterance, STTResult
from stt.providers.base import STTProvider


class FasterWhisperProvider(STTProvider):
    def __init__(self, model_name: str) -> None:
        if not model_name.strip():
            raise ValueError("Nama model Faster Whisper tidak boleh kosong.")
        self._model_name: str = model_name
        self._model: WhisperModel | None = None
        self._load_lock: asyncio.Lock = asyncio.Lock()
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="faster-whisper"
        )
        self._closed: bool = False

    async def _get_model(self) -> WhisperModel:
        async with self._load_lock:
            if self._model is None:
                if self._closed:
                    raise RuntimeError("Faster Whisper provider sudah ditutup.")
                print(f"[STT] memuat Faster Whisper model={self._model_name}")
                loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
                self._model = await loop.run_in_executor(
                    self._executor,
                    partial(
                        WhisperModel,
                        self._model_name,
                        device="cpu",
                        compute_type="int8",
                    ),
                )
            return self._model

    async def transcribe(self, utterance: AudioUtterance, language: str) -> STTResult:
        started: float = time.perf_counter()
        model: WhisperModel = await self._get_model()
        waveform = pcm_stereo_48k_to_mono_16k(utterance.pcm)
        selected_language: str | None = None if language == "auto" else language

        def run_transcription() -> tuple[str, TranscriptionInfo]:
            segments: Iterable[Segment]
            segments, info = model.transcribe(
                waveform,
                language=selected_language,
                task="transcribe",
                vad_filter=True,
                beam_size=5,
                condition_on_previous_text=False,
            )
            text: str = " ".join(segment.text.strip() for segment in segments).strip()
            return text, info

        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        text, info = await loop.run_in_executor(self._executor, run_transcription)
        if not text:
            raise RuntimeError(
                f"Faster Whisper menghasilkan transcript kosong: "
                f"user={utterance.user_id}, duration={utterance.duration_seconds:.3f}s"
            )
        confidence: float | None = getattr(info, "language_probability", None)
        return STTResult(
            text=text,
            language=info.language,
            confidence=confidence,
            duration_seconds=utterance.duration_seconds,
            latency_seconds=time.perf_counter() - started,
            guild_id=utterance.guild_id,
            voice_channel_id=utterance.voice_channel_id,
            user_id=utterance.user_id,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await asyncio.to_thread(
            self._executor.shutdown, wait=True, cancel_futures=True
        )
        self._model = None
