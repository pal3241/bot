from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AudioUtterance:
    guild_id: int
    voice_channel_id: int
    user_id: int
    pcm: bytes
    sample_rate: int
    channels: int
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class STTResult:
    text: str
    language: str
    confidence: float | None
    duration_seconds: float
    latency_seconds: float
    guild_id: int
    voice_channel_id: int
    user_id: int
