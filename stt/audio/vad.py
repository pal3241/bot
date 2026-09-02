import asyncio
import audioop
from dataclasses import dataclass, field
from collections.abc import Callable

from stt.models import AudioUtterance
from stt.settings import STTSettings


@dataclass(slots=True)
class UserAudioBuffer:
    frames: bytearray = field(default_factory=bytearray)
    active: bool = False
    finalize_handle: asyncio.TimerHandle | None = None


class PerUserVAD:
    def __init__(
        self,
        settings: STTSettings,
        guild_id: int,
        voice_channel_id: int,
        on_utterance: Callable[[AudioUtterance], None],
    ) -> None:
        self._settings: STTSettings = settings
        self._guild_id: int = guild_id
        self._voice_channel_id: int = voice_channel_id
        self._on_utterance: Callable[[AudioUtterance], None] = on_utterance
        self._buffers: dict[int, UserAudioBuffer] = {}

    def ingest(self, user_id: int, pcm: bytes) -> None:
        if not pcm:
            return
        buffer: UserAudioBuffer = self._buffers.setdefault(user_id, UserAudioBuffer())
        is_speech: bool = (
            not self._settings.vad_enabled
            or audioop.rms(pcm, 2) >= self._settings.vad_rms_threshold
        )
        if not buffer.active and not is_speech:
            return
        buffer.active = True
        buffer.frames.extend(pcm)
        if buffer.finalize_handle is not None:
            buffer.finalize_handle.cancel()
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        buffer.finalize_handle = loop.call_later(
            self._settings.end_silence_seconds,
            self._finalize,
            user_id,
        )
        if self._duration(buffer.frames) >= self._settings.max_utterance_seconds:
            self._finalize(user_id)

    def _finalize(self, user_id: int) -> None:
        buffer: UserAudioBuffer | None = self._buffers.pop(user_id, None)
        if buffer is None:
            return
        if buffer.finalize_handle is not None:
            buffer.finalize_handle.cancel()
        duration: float = self._duration(buffer.frames)
        if duration < self._settings.min_speech_seconds:
            return
        self._on_utterance(
            AudioUtterance(
                guild_id=self._guild_id,
                voice_channel_id=self._voice_channel_id,
                user_id=user_id,
                pcm=bytes(buffer.frames),
                sample_rate=48000,
                channels=2,
                duration_seconds=duration,
            )
        )

    def clear(self) -> None:
        for buffer in self._buffers.values():
            if buffer.finalize_handle is not None:
                buffer.finalize_handle.cancel()
        self._buffers.clear()

    @staticmethod
    def _duration(frames: bytearray) -> float:
        return len(frames) / float(48000 * 2 * 2)
