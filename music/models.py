from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MusicTrack:
    title: str
    webpage_url: str
    platform: str
    duration_seconds: int | None = None
    uploader: str | None = None
    thumbnail: str | None = None

    @property
    def duration_text(self) -> str:
        if self.duration_seconds is None or self.duration_seconds < 0:
            return "?"
        minutes, seconds = divmod(int(self.duration_seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @property
    def short_label(self) -> str:
        suffix = f" · {self.duration_text}" if self.duration_seconds is not None else ""
        return f"{self.title} · {self.platform}{suffix}"


@dataclass(frozen=True, slots=True)
class MusicSnapshot:
    guild_id: int
    connected: bool
    voice_channel_id: int | None
    voice_channel_name: str | None
    current: MusicTrack | None
    queue: tuple[MusicTrack, ...]
    paused: bool
    playing: bool
    volume_percent: int
