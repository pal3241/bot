from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from music.models import MusicTrack
from music.settings import MusicSettings


def _looks_like_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _platform_name(info: dict[str, object]) -> str:
    value = info.get("extractor_key") or info.get("extractor")
    if isinstance(value, str) and value.strip():
        return value.strip()
    webpage_url = info.get("webpage_url")
    if isinstance(webpage_url, str) and webpage_url.strip():
        try:
            host = urlparse(webpage_url).netloc
        except ValueError:
            host = ""
        if host:
            return host.removeprefix("www.")
    return "unknown"


def _webpage_url(info: dict[str, object]) -> str | None:
    for key in ("webpage_url", "original_url"):
        value = info.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value

    url = info.get("url")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return url

    video_id = info.get("id")
    extractor = str(info.get("extractor_key") or info.get("extractor") or "").casefold()
    if isinstance(video_id, str) and video_id and "youtube" in extractor:
        return f"https://www.youtube.com/watch?v={video_id}"
    return None


def _track_from_info(info: dict[str, object]) -> MusicTrack | None:
    title = info.get("title")
    webpage_url = _webpage_url(info)
    if not isinstance(title, str) or not title.strip() or webpage_url is None:
        return None

    duration_value = info.get("duration")
    duration: int | None = None
    if isinstance(duration_value, (int, float)) and not isinstance(duration_value, bool):
        duration = max(0, int(duration_value))

    uploader_value = info.get("uploader") or info.get("channel") or info.get("artist")
    uploader = uploader_value.strip() if isinstance(uploader_value, str) and uploader_value.strip() else None
    thumbnail_value = info.get("thumbnail")
    thumbnail = (
        thumbnail_value.strip()
        if isinstance(thumbnail_value, str) and thumbnail_value.strip()
        else None
    )

    return MusicTrack(
        title=title.strip(),
        webpage_url=webpage_url,
        platform=_platform_name(info),
        duration_seconds=duration,
        uploader=uploader,
        thumbnail=thumbnail,
    )


class MusicResolver:
    """Resolve titles/URLs with yt-dlp without downloading media to disk."""

    def __init__(self, settings: MusicSettings) -> None:
        self.settings = settings

    def update_settings(self, settings: MusicSettings) -> None:
        self.settings = settings

    @staticmethod
    def _import_yt_dlp():
        try:
            import yt_dlp  # type: ignore
        except ImportError as error:
            raise RuntimeError(
                "yt-dlp belum terpasang. Jalankan: pip install -r requirements.txt"
            ) from error
        return yt_dlp

    def _base_options(self) -> dict[str, object]:
        return {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": False,
            "extract_flat": "in_playlist",
            "ignoreerrors": True,
            "socket_timeout": 15,
            "retries": 3,
            "fragment_retries": 3,
        }

    def _stream_format_selector(self) -> str:
        profile = self.settings.stream_profile
        if profile == "data_saver":
            return (
                "bestaudio[abr<=48]/bestaudio[abr<=64]/"
                "bestaudio[abr<=96]/bestaudio/best"
            )
        if profile == "ultra_low":
            return (
                "bestaudio[abr<=64]/bestaudio[abr<=80]/"
                "bestaudio[abr<=96]/bestaudio/best"
            )
        if profile == "low":
            return "bestaudio[abr<=96]/bestaudio[abr<=128]/bestaudio/best"
        if profile == "balanced":
            return "bestaudio[abr<=128]/bestaudio[abr<=160]/bestaudio/best"
        return "bestaudio/best"

    def _extract_sync(self, target: str) -> object:
        yt_dlp = self._import_yt_dlp()
        with yt_dlp.YoutubeDL(self._base_options()) as ydl:
            return ydl.extract_info(target, download=False)

    @staticmethod
    def _collect_tracks(info: object, limit: int) -> list[MusicTrack]:
        if not isinstance(info, dict):
            return []
        entries = info.get("entries")
        candidates: list[object]
        if isinstance(entries, list):
            candidates = entries[:limit]
        else:
            candidates = [info]

        tracks: list[MusicTrack] = []
        seen: set[str] = set()
        for item in candidates:
            if not isinstance(item, dict):
                continue
            track = _track_from_info(item)
            if track is None or track.webpage_url in seen:
                continue
            seen.add(track.webpage_url)
            tracks.append(track)
        return tracks

    async def search(self, query: str) -> list[MusicTrack]:
        clean = query.strip()
        if not clean:
            raise ValueError("Query musik kosong.")
        target = clean if _looks_like_url(clean) else f"ytsearch{self.settings.search_limit}:{clean}"
        try:
            info = await asyncio.to_thread(self._extract_sync, target)
        except Exception as error:
            if isinstance(error, (ValueError, RuntimeError)):
                raise
            raise RuntimeError(f"Pencarian musik gagal: {type(error).__name__}: {error}") from error
        limit = self.settings.max_playlist_items if _looks_like_url(clean) else self.settings.search_limit
        return self._collect_tracks(info, limit)

    async def resolve_for_play(self, query: str) -> list[MusicTrack]:
        clean = query.strip()
        if not clean:
            raise ValueError("Judul/URL musik kosong.")
        target = clean if _looks_like_url(clean) else f"ytsearch1:{clean}"
        try:
            info = await asyncio.to_thread(self._extract_sync, target)
        except Exception as error:
            if isinstance(error, (ValueError, RuntimeError)):
                raise
            raise RuntimeError(f"Resolver musik gagal: {type(error).__name__}: {error}") from error
        tracks = self._collect_tracks(info, self.settings.max_playlist_items)
        if not tracks:
            raise LookupError("Musik tidak ditemukan atau platform tidak dapat diekstrak.")
        return tracks

    def _resolve_stream_sync(self, webpage_url: str) -> str:
        yt_dlp = self._import_yt_dlp()
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "format": self._stream_format_selector(),
            "noplaylist": True,
            "socket_timeout": 15,
            "retries": 3,
            "fragment_retries": 3,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(webpage_url, download=False)
        if not isinstance(info, dict):
            raise RuntimeError("yt-dlp tidak mengembalikan metadata stream.")
        stream_url = info.get("url")
        if not isinstance(stream_url, str) or not stream_url.strip():
            raise RuntimeError("URL audio stream tidak tersedia untuk media ini.")
        return stream_url.strip()

    async def resolve_stream_url(self, track: MusicTrack) -> str:
        try:
            return await asyncio.to_thread(self._resolve_stream_sync, track.webpage_url)
        except Exception as error:
            if isinstance(error, RuntimeError):
                raise
            raise RuntimeError(
                f"Gagal mendapatkan stream audio: {type(error).__name__}: {error}"
            ) from error
