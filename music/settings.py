from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


STREAM_PROFILES = ("low", "balanced", "high")


@dataclass(frozen=True, slots=True)
class MusicSettings:
    default_volume_percent: int = 35
    max_volume_percent: int = 150
    search_limit: int = 5
    max_playlist_items: int = 25
    ffmpeg_path: str = "ffmpeg"
    disconnect_on_stop: bool = False
    # low: prefer <=96 kbps audio, balanced: <=128 kbps, high: best audio.
    # Existing config files without this key automatically use low bandwidth mode.
    stream_profile: str = "low"


def _int(value: object, fallback: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, number))


def _bool(value: object, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _stream_profile(value: object, fallback: str = "low") -> str:
    if not isinstance(value, str):
        return fallback
    normalized = value.strip().casefold()
    return normalized if normalized in STREAM_PROFILES else fallback


def normalize_settings(value: MusicSettings) -> MusicSettings:
    max_volume = _int(value.max_volume_percent, 150, 1, 200)
    default_volume = _int(value.default_volume_percent, 35, 0, max_volume)
    return MusicSettings(
        default_volume_percent=default_volume,
        max_volume_percent=max_volume,
        search_limit=_int(value.search_limit, 5, 1, 15),
        max_playlist_items=_int(value.max_playlist_items, 25, 1, 100),
        ffmpeg_path=(value.ffmpeg_path or "ffmpeg").strip() or "ffmpeg",
        disconnect_on_stop=bool(value.disconnect_on_stop),
        stream_profile=_stream_profile(value.stream_profile),
    )


def load_music_settings(path: Path) -> MusicSettings:
    fallback = MusicSettings()
    if not path.exists():
        return fallback
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    if not isinstance(raw, dict):
        return fallback
    settings = MusicSettings(
        default_volume_percent=_int(
            raw.get("default_volume_percent"),
            fallback.default_volume_percent,
            0,
            200,
        ),
        max_volume_percent=_int(
            raw.get("max_volume_percent"),
            fallback.max_volume_percent,
            1,
            200,
        ),
        search_limit=_int(raw.get("search_limit"), fallback.search_limit, 1, 15),
        max_playlist_items=_int(
            raw.get("max_playlist_items"), fallback.max_playlist_items, 1, 100
        ),
        ffmpeg_path=(
            str(raw.get("ffmpeg_path", fallback.ffmpeg_path)).strip()
            or fallback.ffmpeg_path
        ),
        disconnect_on_stop=_bool(
            raw.get("disconnect_on_stop"), fallback.disconnect_on_stop
        ),
        stream_profile=_stream_profile(
            raw.get("stream_profile"), fallback.stream_profile
        ),
    )
    return normalize_settings(settings)


def save_music_settings(path: Path, settings: MusicSettings) -> MusicSettings:
    normalized = normalize_settings(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(normalized), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return normalized
