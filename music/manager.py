from __future__ import annotations

import asyncio
import importlib.util
import shutil
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import discord

from music.models import MusicSnapshot, MusicTrack
from music.resolver import MusicResolver
from music.settings import (
    MusicSettings,
    discord_bitrate_kbps,
    load_music_settings,
    normalize_settings,
    save_music_settings,
)

if TYPE_CHECKING:
    from scheduler.manager import SchedulerManager
    from scheduler.models import ScheduledJob


@dataclass(slots=True)
class _GuildMusicState:
    queue: deque[MusicTrack] = field(default_factory=deque)
    current: MusicTrack | None = None
    volume: float = 0.70
    stop_requested: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class MusicManager:
    def __init__(
        self,
        client: discord.Client,
        settings_path: Path = Path("config/music.json"),
    ) -> None:
        self.client = client
        self.settings_path = settings_path
        self.settings: MusicSettings = load_music_settings(settings_path)
        self.resolver = MusicResolver(self.settings)
        self._states: dict[int, _GuildMusicState] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._scheduler: SchedulerManager | None = None
        self.available = True

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        status = self.backend_status()
        print(f"[SENA MUSIC] manager started {status}")

    def backend_status(self) -> str:
        yt_dlp_ok = importlib.util.find_spec("yt_dlp") is not None
        ffmpeg_ok = shutil.which(self.settings.ffmpeg_path) is not None
        return (
            f"resolver={'ok' if yt_dlp_ok else 'missing-yt-dlp'} "
            f"ffmpeg={'ok' if ffmpeg_ok else 'missing'} "
            f"voice=runtime profile={self.settings.stream_profile} "
            f"discord_opus={discord_bitrate_kbps(self.settings.stream_profile)}kbps"
        )

    def attach_scheduler(self, scheduler: SchedulerManager) -> None:
        if self._scheduler is scheduler:
            return
        scheduler.register_job_type(
            "music.play",
            "Play a title or URL in Discord voice. payload: query(string), optional voice_channel_id(int).",
            self._scheduled_play,
        )
        self._scheduler = scheduler

    def _state(self, guild_id: int) -> _GuildMusicState:
        state = self._states.get(guild_id)
        if state is None:
            state = _GuildMusicState(volume=self.settings.default_volume_percent / 100.0)
            self._states[guild_id] = state
        return state

    def _discord_encoder_options(self) -> dict[str, object]:
        profile = self.settings.stream_profile
        expected_packet_loss = 0.25 if profile in {"data_saver", "ultra_low"} else 0.20 if profile == "low" else 0.15
        return {
            "bitrate": discord_bitrate_kbps(profile),
            "fec": True,
            "expected_packet_loss": expected_packet_loss,
            "bandwidth": "full",
            "signal_type": "music",
        }

    async def apply_settings(self, settings: MusicSettings) -> MusicSettings:
        normalized = normalize_settings(settings)
        self.settings = save_music_settings(self.settings_path, normalized)
        self.resolver.update_settings(self.settings)
        max_volume = self.settings.max_volume_percent / 100.0
        for guild_id, state in self._states.items():
            async with state.lock:
                state.volume = min(state.volume, max_volume)
                guild = self.client.get_guild(guild_id)
                voice = guild.voice_client if guild is not None else None
                if voice is not None and isinstance(voice.source, discord.PCMVolumeTransformer):
                    voice.source.volume = state.volume
        print(f"[SENA MUSIC] settings applied {self.backend_status()}")
        return self.settings

    async def search(self, query: str) -> list[MusicTrack]:
        return await self.resolver.search(query)

    def _get_guild(self, guild_id: int) -> discord.Guild:
        guild = self.client.get_guild(int(guild_id))
        if guild is None:
            raise LookupError(f"Discord server tidak ditemukan: {guild_id}")
        return guild

    async def _ensure_voice(
        self,
        guild_id: int,
        voice_channel_id: int | None,
    ) -> discord.VoiceClient:
        guild = self._get_guild(guild_id)
        current = guild.voice_client
        if current is not None and current.is_connected():
            if voice_channel_id is None:
                return current
            channel = guild.get_channel(int(voice_channel_id))
            if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                raise LookupError("Voice channel tujuan tidak ditemukan.")
            if current.channel is None or current.channel.id != channel.id:
                await current.move_to(channel)
            return current

        if voice_channel_id is None:
            raise RuntimeError(
                "Bot belum berada di voice channel. Masuk VC dulu atau tentukan voice_channel_id."
            )
        channel = guild.get_channel(int(voice_channel_id))
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            raise LookupError("Voice channel tujuan tidak ditemukan.")
        try:
            voice = await channel.connect()
        except Exception as error:
            raise RuntimeError(
                "Discord voice backend gagal connect. "
                f"{type(error).__name__}: {error}"
            ) from error
        return voice

    def _ensure_ffmpeg(self) -> None:
        if shutil.which(self.settings.ffmpeg_path) is None:
            raise RuntimeError(
                f"FFmpeg tidak ditemukan: {self.settings.ffmpeg_path!r}. "
                "Di Termux jalankan: pkg install ffmpeg"
            )

    async def play(
        self,
        *,
        guild_id: int,
        query: str,
        voice_channel_id: int | None,
        requester_id: int | None = None,
    ) -> list[MusicTrack]:
        del requester_id
        self._ensure_ffmpeg()
        tracks = await self.resolver.resolve_for_play(query)
        await self._ensure_voice(guild_id, voice_channel_id)
        state = self._state(guild_id)
        async with state.lock:
            state.queue.extend(tracks)
            if state.current is None:
                await self._play_next_locked(guild_id, state)
        return tracks

    async def _play_next_locked(self, guild_id: int, state: _GuildMusicState) -> None:
        if state.current is not None:
            return
        guild = self._get_guild(guild_id)
        voice = guild.voice_client
        if voice is None or not voice.is_connected():
            raise RuntimeError("Voice client tidak terhubung saat mencoba memutar queue.")

        while state.queue:
            track = state.queue.popleft()
            try:
                stream_url = await self.resolver.resolve_stream_url(track)
                source = discord.FFmpegPCMAudio(
                    stream_url,
                    executable=self.settings.ffmpeg_path,
                    before_options=(
                        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
                    ),
                    options="-vn",
                )
                transformed = discord.PCMVolumeTransformer(source, volume=state.volume)
            except Exception as error:
                print(
                    f"[SENA MUSIC] source failed guild={guild_id} title={track.title!r} "
                    f"type={type(error).__name__} detail={error}"
                )
                continue

            loop = self._loop or asyncio.get_running_loop()

            def after_playback(error: Exception | None) -> None:
                future = asyncio.run_coroutine_threadsafe(
                    self._after_track(guild_id, error),
                    loop,
                )

                def consume_result(done) -> None:
                    try:
                        done.result()
                    except Exception as callback_error:
                        print(
                            f"[SENA MUSIC] after callback failed guild={guild_id} "
                            f"type={type(callback_error).__name__} detail={callback_error}"
                        )

                future.add_done_callback(consume_result)

            encoder_options = self._discord_encoder_options()
            try:
                state.current = track
                state.stop_requested = False
                voice.play(
                    transformed,
                    after=after_playback,
                    **encoder_options,
                )
            except Exception:
                state.current = None
                try:
                    transformed.cleanup()
                except Exception:
                    pass
                raise
            print(
                f"[SENA MUSIC] playing guild={guild_id} platform={track.platform} "
                f"title={track.title!r} queue={len(state.queue)} volume={int(state.volume*100)} "
                f"profile={self.settings.stream_profile} "
                f"discord_opus={encoder_options['bitrate']}kbps"
            )
            return

        state.current = None

    async def _after_track(self, guild_id: int, error: Exception | None) -> None:
        state = self._state(guild_id)
        async with state.lock:
            if error is not None:
                print(
                    f"[SENA MUSIC] playback error guild={guild_id} "
                    f"type={type(error).__name__} detail={error}"
                )
            state.current = None
            if state.stop_requested:
                state.stop_requested = False
                return
            try:
                await self._play_next_locked(guild_id, state)
            except Exception as next_error:
                print(
                    f"[SENA MUSIC] next track failed guild={guild_id} "
                    f"type={type(next_error).__name__} detail={next_error}"
                )

    async def pause(self, guild_id: int) -> bool:
        guild = self._get_guild(guild_id)
        voice = guild.voice_client
        if voice is None or not voice.is_connected() or not voice.is_playing():
            return False
        voice.pause()
        return True

    async def resume(self, guild_id: int) -> bool:
        guild = self._get_guild(guild_id)
        voice = guild.voice_client
        if voice is None or not voice.is_connected() or not voice.is_paused():
            return False
        voice.resume()
        return True

    async def skip(self, guild_id: int) -> bool:
        state = self._state(guild_id)
        guild = self._get_guild(guild_id)
        voice = guild.voice_client
        async with state.lock:
            if voice is None or not voice.is_connected() or not (
                voice.is_playing() or voice.is_paused()
            ):
                return False
            state.stop_requested = False
            state.current = None
            voice.stop()
            return True

    async def stop(self, guild_id: int) -> bool:
        state = self._state(guild_id)
        guild = self._get_guild(guild_id)
        voice = guild.voice_client
        had_activity = bool(state.queue or state.current)
        async with state.lock:
            state.queue.clear()
            state.stop_requested = True
            state.current = None
            if voice is not None and voice.is_connected() and (
                voice.is_playing() or voice.is_paused()
            ):
                voice.stop()
                had_activity = True
        if (
            self.settings.disconnect_on_stop
            and voice is not None
            and voice.is_connected()
        ):
            await voice.disconnect(force=False)
        return had_activity

    async def set_volume(self, guild_id: int, percent: int) -> int:
        maximum = self.settings.max_volume_percent
        value = max(0, min(maximum, int(percent)))
        state = self._state(guild_id)
        async with state.lock:
            state.volume = value / 100.0
            guild = self._get_guild(guild_id)
            voice = guild.voice_client
            if voice is not None and isinstance(voice.source, discord.PCMVolumeTransformer):
                voice.source.volume = state.volume
        return value

    async def snapshot(self, guild_id: int) -> MusicSnapshot:
        state = self._state(guild_id)
        guild = self._get_guild(guild_id)
        voice = guild.voice_client
        async with state.lock:
            connected = voice is not None and voice.is_connected()
            channel = voice.channel if connected else None
            return MusicSnapshot(
                guild_id=guild_id,
                connected=connected,
                voice_channel_id=channel.id if channel is not None else None,
                voice_channel_name=channel.name if channel is not None else None,
                current=state.current,
                queue=tuple(state.queue),
                paused=bool(voice is not None and voice.is_paused()),
                playing=bool(voice is not None and voice.is_playing()),
                volume_percent=round(state.volume * 100),
            )

    async def _scheduled_play(self, job: ScheduledJob) -> None:
        query = job.payload.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("music.play schedule membutuhkan payload.query.")
        voice_value = job.payload.get("voice_channel_id")
        voice_channel_id = (
            int(voice_value)
            if isinstance(voice_value, int)
            and not isinstance(voice_value, bool)
            and voice_value > 0
            else None
        )
        if job.guild_id is None:
            raise ValueError("music.play schedule membutuhkan guild_id.")
        await self.play(
            guild_id=job.guild_id,
            query=query,
            voice_channel_id=voice_channel_id,
            requester_id=job.creator_id,
        )

    async def close(self) -> None:
        for guild_id, state in list(self._states.items()):
            try:
                guild = self.client.get_guild(guild_id)
                voice = guild.voice_client if guild is not None else None
                async with state.lock:
                    state.queue.clear()
                    state.stop_requested = True
                    state.current = None
                    if voice is not None and (voice.is_playing() or voice.is_paused()):
                        voice.stop()
            except Exception as error:
                print(
                    f"[SENA MUSIC] close failed guild={guild_id} "
                    f"type={type(error).__name__} detail={error}"
                )
        self.available = False
        print("[SENA MUSIC] manager stopped")
