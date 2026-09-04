from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import discord
import flet as ft

from music.models import MusicTrack
from ui.flet_app import BORDER, ERROR, MUTED, SUCCESS, TEXT, WARNING
from ui.flet_app_schedule import SenaFletUI as _BaseSenaFletUI


class SenaFletUI(_BaseSenaFletUI):
    """Control center with music search, playback controls, queue, and settings."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        manager = self.ctx.music
        settings = manager.settings if manager is not None else None

        self._music_search_cache: dict[str, MusicTrack] = {}
        self.music_guild = ft.Dropdown(
            label="Server",
            expand=True,
            on_select=self._music_guild_changed,
        )
        self.music_voice = ft.Dropdown(label="Voice Channel", expand=True)
        self.music_query = ft.TextField(
            label="Judul atau link musik",
            hint_text="Yoasobi Idol atau https://...",
            border_color=BORDER,
            expand=True,
            on_submit=self._music_play,
        )
        self.music_results = ft.Dropdown(
            label="Hasil pencarian (opsional)",
            expand=True,
        )
        self.music_status = ft.Text("", color=MUTED, size=11)
        self.music_now = ft.Text("Tidak ada musik diputar.", color=TEXT, size=13, selectable=True)
        self.music_queue_text = ft.Text("Queue kosong.", color="#D8D8D8", size=11, selectable=True)
        self.music_backend = ft.Text(
            manager.backend_status() if manager is not None else "Music Manager offline",
            color=MUTED,
            size=10,
        )
        self.music_volume = ft.TextField(
            label="Volume %",
            value=str(settings.default_volume_percent if settings else 70),
            width=130,
            border_color=BORDER,
        )

        self.music_setting_default_volume = ft.TextField(
            label="Default volume %",
            value=str(settings.default_volume_percent if settings else 70),
            border_color=BORDER,
        )
        self.music_setting_max_volume = ft.TextField(
            label="Max volume %",
            value=str(settings.max_volume_percent if settings else 150),
            border_color=BORDER,
        )
        self.music_setting_search_limit = ft.TextField(
            label="Search results",
            value=str(settings.search_limit if settings else 5),
            border_color=BORDER,
        )
        self.music_setting_playlist_limit = ft.TextField(
            label="Max playlist items",
            value=str(settings.max_playlist_items if settings else 25),
            border_color=BORDER,
        )
        self.music_setting_ffmpeg = ft.TextField(
            label="FFmpeg executable/path",
            value=settings.ffmpeg_path if settings else "ffmpeg",
            border_color=BORDER,
        )
        self.music_setting_disconnect = ft.Checkbox(
            label="Disconnect dari VC saat Stop",
            value=settings.disconnect_on_stop if settings else False,
        )
        self.music_setting_status = ft.Text("", color=MUTED, size=11)

    def _music_manager(self):
        if self.ctx.music is None:
            raise RuntimeError("Music Manager tidak aktif.")
        return self.ctx.music

    def _music_selected_guild_id(self) -> int:
        if not self.music_guild.value:
            raise ValueError("Pilih server.")
        return int(self.music_guild.value)

    async def _music_guild_changed(self, e: Any = None) -> None:
        del e
        guild = (
            self.ctx.client.get_guild(int(self.music_guild.value))
            if self.music_guild.value
            else None
        )
        channels = (
            [
                channel
                for channel in guild.channels
                if isinstance(channel, (discord.VoiceChannel, discord.StageChannel))
            ]
            if guild is not None
            else []
        )
        self.music_voice.options = self._options(
            [(channel.id, channel.name) for channel in channels]
        )
        valid = {str(channel.id) for channel in channels}
        if self.music_voice.value not in valid:
            self.music_voice.value = str(channels[0].id) if channels else None
        await self._music_refresh()

    async def _music_search(self, e: Any = None) -> None:
        del e
        query = (self.music_query.value or "").strip()
        if not query:
            self.music_status.value = "Isi judul atau link dulu."
            self.music_status.color = WARNING
        else:
            try:
                manager = self._music_manager()
                self.music_status.value = "Searching..."
                self.music_status.color = MUTED
                if self.page:
                    self.page.update()
                tracks = await manager.search(query)
                self._music_search_cache = {
                    str(index): track for index, track in enumerate(tracks)
                }
                self.music_results.options = self._options(
                    [
                        (index, track.short_label)
                        for index, track in self._music_search_cache.items()
                    ]
                )
                self.music_results.value = "0" if tracks else None
                self.music_status.value = (
                    f"{len(tracks)} hasil ditemukan. Pilih hasil lalu Play."
                    if tracks
                    else "Tidak ada hasil."
                )
                self.music_status.color = SUCCESS if tracks else WARNING
            except Exception as error:
                self.music_status.value = f"Search gagal · {type(error).__name__}: {error}"
                self.music_status.color = ERROR
        if self.page:
            self.page.update()

    async def _music_play(self, e: Any = None) -> None:
        del e
        try:
            manager = self._music_manager()
            guild_id = self._music_selected_guild_id()
            selected = self._music_search_cache.get(str(self.music_results.value or ""))
            query = selected.webpage_url if selected is not None else (self.music_query.value or "").strip()
            if not query:
                raise ValueError("Isi judul/link atau pilih hasil pencarian.")
            voice_channel_id = int(self.music_voice.value) if self.music_voice.value else None
            self.music_status.value = "Resolving & connecting..."
            self.music_status.color = MUTED
            if self.page:
                self.page.update()
            tracks = await manager.play(
                guild_id=guild_id,
                query=query,
                voice_channel_id=voice_channel_id,
                requester_id=None,
            )
            first = tracks[0]
            extra = f" +{len(tracks)-1} queue" if len(tracks) > 1 else ""
            self.music_status.value = f"Added · {first.title} [{first.platform}]{extra}"
            self.music_status.color = SUCCESS
            await self._music_refresh()
        except Exception as error:
            self.music_status.value = f"Play gagal · {type(error).__name__}: {error}"
            self.music_status.color = ERROR
        if self.page:
            self.page.update()

    async def _music_pause(self, e: Any = None) -> None:
        del e
        try:
            changed = await self._music_manager().pause(self._music_selected_guild_id())
            self.music_status.value = "Paused." if changed else "Tidak ada track aktif untuk pause."
            self.music_status.color = SUCCESS if changed else WARNING
            await self._music_refresh()
        except Exception as error:
            self.music_status.value = f"Pause gagal · {type(error).__name__}: {error}"
            self.music_status.color = ERROR
        if self.page:
            self.page.update()

    async def _music_resume(self, e: Any = None) -> None:
        del e
        try:
            changed = await self._music_manager().resume(self._music_selected_guild_id())
            self.music_status.value = "Resumed." if changed else "Music tidak sedang pause."
            self.music_status.color = SUCCESS if changed else WARNING
            await self._music_refresh()
        except Exception as error:
            self.music_status.value = f"Resume gagal · {type(error).__name__}: {error}"
            self.music_status.color = ERROR
        if self.page:
            self.page.update()

    async def _music_skip(self, e: Any = None) -> None:
        del e
        try:
            changed = await self._music_manager().skip(self._music_selected_guild_id())
            self.music_status.value = "Skipped." if changed else "Tidak ada track aktif."
            self.music_status.color = SUCCESS if changed else WARNING
            await asyncio.sleep(0.15)
            await self._music_refresh()
        except Exception as error:
            self.music_status.value = f"Skip gagal · {type(error).__name__}: {error}"
            self.music_status.color = ERROR
        if self.page:
            self.page.update()

    async def _music_stop(self, e: Any = None) -> None:
        del e
        try:
            await self._music_manager().stop(self._music_selected_guild_id())
            self.music_status.value = "Stopped · queue dibersihkan."
            self.music_status.color = SUCCESS
            await self._music_refresh()
        except Exception as error:
            self.music_status.value = f"Stop gagal · {type(error).__name__}: {error}"
            self.music_status.color = ERROR
        if self.page:
            self.page.update()

    async def _music_set_volume(self, e: Any = None) -> None:
        del e
        try:
            value = int(float(self.music_volume.value or "0"))
            actual = await self._music_manager().set_volume(
                self._music_selected_guild_id(), value
            )
            self.music_volume.value = str(actual)
            self.music_status.value = f"Volume {actual}%."
            self.music_status.color = SUCCESS
        except Exception as error:
            self.music_status.value = f"Volume gagal · {type(error).__name__}: {error}"
            self.music_status.color = ERROR
        if self.page:
            self.page.update()

    async def _music_refresh(self, e: Any = None) -> None:
        del e
        if self.ctx.music is None or not self.music_guild.value:
            self.music_now.value = "Music Manager offline atau server belum dipilih."
            self.music_queue_text.value = "Queue kosong."
            if self.page:
                self.page.update()
            return
        try:
            manager = self._music_manager()
            snapshot = await manager.snapshot(int(self.music_guild.value))
            self.music_backend.value = manager.backend_status()
            state = "PAUSED" if snapshot.paused else "PLAYING" if snapshot.playing else "IDLE"
            if snapshot.current is None:
                self.music_now.value = (
                    f"{state} · VC={snapshot.voice_channel_name or '-'} · volume={snapshot.volume_percent}%\n"
                    "Tidak ada track aktif."
                )
            else:
                track = snapshot.current
                self.music_now.value = (
                    f"{state} · VC={snapshot.voice_channel_name or '-'} · volume={snapshot.volume_percent}%\n"
                    f"{track.title}\n{track.platform} · {track.duration_text}\n{track.webpage_url}"
                )
            lines = [
                f"{index}. {track.title} · {track.platform} · {track.duration_text}"
                for index, track in enumerate(snapshot.queue, start=1)
            ]
            self.music_queue_text.value = "\n".join(lines) or "Queue kosong."
            self.music_volume.value = str(snapshot.volume_percent)
        except Exception as error:
            self.music_now.value = f"Refresh gagal · {type(error).__name__}: {error}"
        if self.page:
            self.page.update()

    async def _music_save_settings(self, e: Any = None) -> None:
        del e
        try:
            manager = self._music_manager()
            current = manager.settings
            updated = replace(
                current,
                default_volume_percent=int(float(self.music_setting_default_volume.value or "0")),
                max_volume_percent=int(float(self.music_setting_max_volume.value or "0")),
                search_limit=int(float(self.music_setting_search_limit.value or "0")),
                max_playlist_items=int(float(self.music_setting_playlist_limit.value or "0")),
                ffmpeg_path=(self.music_setting_ffmpeg.value or "ffmpeg").strip(),
                disconnect_on_stop=bool(self.music_setting_disconnect.value),
            )
            saved = await manager.apply_settings(updated)
            self.music_setting_default_volume.value = str(saved.default_volume_percent)
            self.music_setting_max_volume.value = str(saved.max_volume_percent)
            self.music_setting_search_limit.value = str(saved.search_limit)
            self.music_setting_playlist_limit.value = str(saved.max_playlist_items)
            self.music_setting_ffmpeg.value = saved.ffmpeg_path
            self.music_setting_disconnect.value = saved.disconnect_on_stop
            self.music_setting_status.value = "Music settings saved & active."
            self.music_setting_status.color = SUCCESS
            self.music_backend.value = manager.backend_status()
        except Exception as error:
            self.music_setting_status.value = f"Save gagal · {type(error).__name__}: {error}"
            self.music_setting_status.color = ERROR
        if self.page:
            self.page.update()

    def _music(self) -> ft.Control:
        self.music_guild.options = self._guild_options()
        if self.music_guild.value is None and self.ctx.client.guilds:
            guild = self.ctx.client.guilds[0]
            self.music_guild.value = str(guild.id)
            channels = [
                channel
                for channel in guild.channels
                if isinstance(channel, (discord.VoiceChannel, discord.StageChannel))
            ]
            self.music_voice.options = self._options(
                [(channel.id, channel.name) for channel in channels]
            )
            self.music_voice.value = str(channels[0].id) if channels else None

        if self.page:
            self.page.run_task(self._music_refresh)

        return self._body(
            [
                self._title(
                    "Music",
                    "Multi-platform title/URL search, queue, playback controls, dan universal scheduling",
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text("Backend", color=TEXT, weight=ft.FontWeight.W_600),
                                    self.music_backend,
                                ],
                                spacing=10,
                            ),
                            ft.Text(
                                "Resolver memakai yt-dlp: judul dicari lewat search, URL diekstrak langsung. Platform DRM/subscription-protected tidak dapat diputar.",
                                color=MUTED,
                                size=10,
                            ),
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.music_guild),
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.music_voice),
                                ]
                            ),
                            ft.Row(
                                controls=[
                                    self.music_query,
                                    ft.Button("Search", icon=ft.Icons.SEARCH, on_click=self._music_search),
                                ]
                            ),
                            self.music_results,
                            ft.Row(
                                controls=[
                                    ft.Button("Play / Queue", icon=ft.Icons.PLAY_ARROW, on_click=self._music_play),
                                    ft.IconButton(icon=ft.Icons.PAUSE, tooltip="Pause", on_click=self._music_pause),
                                    ft.IconButton(icon=ft.Icons.PLAY_CIRCLE_OUTLINE, tooltip="Resume", on_click=self._music_resume),
                                    ft.IconButton(icon=ft.Icons.SKIP_NEXT, tooltip="Skip", on_click=self._music_skip),
                                    ft.IconButton(icon=ft.Icons.STOP, tooltip="Stop", on_click=self._music_stop),
                                ],
                                wrap=True,
                            ),
                            ft.Row(
                                controls=[
                                    self.music_volume,
                                    ft.Button("Set volume", icon=ft.Icons.VOLUME_UP, on_click=self._music_set_volume),
                                    ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Refresh", on_click=self._music_refresh),
                                ],
                                wrap=True,
                            ),
                            self.music_status,
                        ],
                        spacing=12,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("Now playing", color=TEXT, weight=ft.FontWeight.W_600),
                            self.music_now,
                            ft.Divider(color=BORDER),
                            ft.Text("Queue", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.Container(
                                height=220,
                                padding=10,
                                bgcolor="#080808",
                                border=ft.Border.all(1, BORDER),
                                border_radius=12,
                                content=ft.Column(
                                    controls=[self.music_queue_text],
                                    scroll=ft.ScrollMode.AUTO,
                                ),
                            ),
                        ],
                        spacing=10,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("Music settings", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(col={"xs": 6, "md": 3}, content=self.music_setting_default_volume),
                                    ft.Container(col={"xs": 6, "md": 3}, content=self.music_setting_max_volume),
                                    ft.Container(col={"xs": 6, "md": 3}, content=self.music_setting_search_limit),
                                    ft.Container(col={"xs": 6, "md": 3}, content=self.music_setting_playlist_limit),
                                    ft.Container(col=12, content=self.music_setting_ffmpeg),
                                ]
                            ),
                            self.music_setting_disconnect,
                            ft.Button("Save music settings", icon=ft.Icons.SAVE, on_click=self._music_save_settings),
                            self.music_setting_status,
                        ],
                        spacing=12,
                    )
                ),
            ]
        )

    def _view_for_index(self, index: int) -> ft.Control:
        builders = [
            self._dashboard,
            self._terminal_chat,
            self._emoji,
            self._voice,
            self._music,
            self._ai_settings,
            self._schedule,
            self._settings,
        ]
        return builders[index]()

    def _nav(self) -> ft.NavigationRail:
        rail = super()._nav()
        rail.destinations.insert(
            4,
            ft.NavigationRailDestination(
                icon=ft.Icons.MUSIC_NOTE,
                label="Music",
            ),
        )
        return rail

    async def _log_pump(self) -> None:
        while self.page is not None:
            if self._selected_index == 4:
                await self._music_refresh()
            elif self._selected_index == 7:
                await self._refresh_logs()
            await asyncio.sleep(0.9)
