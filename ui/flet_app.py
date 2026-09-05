from __future__ import annotations

import asyncio
import hmac
import os
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import discord
import flet as ft

from assistant.audience_personality import AudiencePersonalityConfig
from assistant.settings import save_settings as save_ai_settings
from config import (
    AI_SETTINGS_FILE,
    GIF_FOLDER,
    MAX_EMOJI_SIZE,
    STT_SETTINGS_FILE,
    TTS_LANGUAGE,
    TTS_PROVIDER,
    VOICE_CONVERTER,
    VOICE_CONVERTER_ENABLED,
    VOICE_CONVERTER_INDEX_RATIO,
    VOICE_CONVERTER_PITCH,
    VOICE_CONVERTER_PROTECT,
    VOICE_SETTINGS_FILE,
)
from core.context import AppContext
from core.device import DeviceInfo
from core.feature_loader import FeatureLoadResult, FeatureLoadState, feature_health_summary
from core.runtime_log import RUNTIME_LOGS
from core.runtime_status import RuntimeStatus
from stt.settings import load_configured_settings, save_settings as save_stt_settings
from voice.converters.registry import CONVERTERS
from voice.converters.settings import VoiceConverterSettings
from voice.manager import VoiceManager
from voice.registry import PROVIDERS
from voice.settings_store import VoicePreferences, load_preferences, save_preferences


BG = "#050505"
SIDEBAR = "#090909"
PANEL = "#101010"
PANEL_2 = "#151515"
BORDER = "#242424"
TEXT = "#F4F4F5"
MUTED = "#8E8E93"
SUCCESS = "#69D49D"
WARNING = "#E6B85C"
ERROR = "#FF7070"
WEB_HOST = os.getenv("SENA_WEB_HOST", "0.0.0.0").strip() or "0.0.0.0"
WEB_PORT = int(os.getenv("SENA_WEB_PORT", "8550"))
WEB_PIN = os.getenv("SENA_WEB_PIN", "").strip()
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class SenaFletUI:
    def __init__(
        self,
        ctx: AppContext,
        device: DeviceInfo,
        feature_results: dict[str, FeatureLoadResult],
        runtime_status: RuntimeStatus,
    ) -> None:
        self.ctx = ctx
        self.device = device
        self.feature_results = feature_results
        self.runtime_status = runtime_status
        self.page: ft.Page | None = None
        self._selected_index = 0
        self._compact = False
        self._chat_lines: list[str] = []
        self._shutdown_event = asyncio.Event()
        self._restart_requested = False
        self.settings_status = ft.Text("", color=MUTED, size=11)

        self.content = ft.Container(expand=True, bgcolor=BG)
        self.chat_view = ft.TextField(
            value="",
            multiline=True,
            read_only=True,
            expand=True,
            text_size=13,
            color="#D8D8D8",
            bgcolor="#080808",
            border_color=BORDER,
        )
        self.chat_input = ft.TextField(
            hint_text="Ketik pesan ke Discord...",
            expand=True,
            bgcolor=PANEL,
            border_color=BORDER,
            color=TEXT,
            on_submit=self._send_chat,
        )
        self.chat_guild = ft.Dropdown(
            label="Server", expand=True, on_select=self._chat_guild_changed
        )
        self.chat_channel = ft.Dropdown(label="Channel", expand=True)

        self.emoji_guild = ft.Dropdown(
            label="Server", expand=True, on_select=self._emoji_guild_changed
        )
        self.emoji_path = ft.TextField(
            label="Path file/folder di device yang menjalankan Sena",
            value=str(GIF_FOLDER),
            border_color=BORDER,
            expand=True,
        )
        self.emoji_name = ft.TextField(
            label="Nama emoji (opsional untuk single file)",
            border_color=BORDER,
            expand=True,
        )
        self.emoji_delete = ft.Dropdown(label="Emoji yang akan dihapus", expand=True)
        self.emoji_text = ft.Text("", size=12, color="#D8D8D8", selectable=True)
        self.emoji_status = ft.Text("", size=11, color=MUTED)

        self.voice_guild = ft.Dropdown(
            label="Server", expand=True, on_select=self._voice_guild_changed
        )
        self.voice_channel = ft.Dropdown(label="Voice Channel", expand=True)
        self.voice_status = ft.Text("Voice idle", color=MUTED)
        self.voice_save_status = ft.Text("", color=MUTED, size=11)
        self.tts_test_status = ft.Text("", color=MUTED, size=11, selectable=True)

        self.ai_status = ft.Text("", color=MUTED, size=11)
        self.personality_status = ft.Text("", color=MUTED, size=11)

        self.log_text = ft.Text("", size=12, color="#C9C9C9", selectable=True)
        self.log_scroll = ft.Column(
            controls=[self.log_text], scroll=ft.ScrollMode.AUTO, expand=True
        )

    # ---------- generic UI ----------
    def _panel(
        self, content: ft.Control, *, expand: bool = False, padding: int = 18
    ) -> ft.Container:
        return ft.Container(
            content=content,
            padding=padding,
            bgcolor=PANEL,
            border=ft.Border.all(1, BORDER),
            border_radius=16,
            expand=expand,
        )

    def _body(self, controls: list[ft.Control]) -> ft.Container:
        return ft.Container(
            expand=True,
            padding=18 if self._compact else 28,
            content=ft.Column(
                controls=controls,
                spacing=16,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    def _title(self, title: str, subtitle: str) -> ft.Row:
        return ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Text(
                            title,
                            size=23 if self._compact else 28,
                            weight=ft.FontWeight.W_600,
                            color=TEXT,
                        ),
                        ft.Text(subtitle, size=12, color=MUTED),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    border=ft.Border.all(1, BORDER),
                    border_radius=18,
                    content=ft.Text(
                        "ONLINE" if self.ctx.client.is_ready() else "STARTING",
                        size=10,
                        color=SUCCESS if self.ctx.client.is_ready() else WARNING,
                    ),
                ),
            ]
        )

    def _options(self, items: list[tuple[int | str, str]]) -> list[ft.DropdownOption]:
        return [ft.DropdownOption(key=str(key), text=text) for key, text in items]

    def _guild_options(self) -> list[ft.DropdownOption]:
        return self._options([(guild.id, guild.name) for guild in self.ctx.client.guilds])

    def _card(self, label: str, value: str, icon: str, detail: str = "") -> ft.Container:
        return ft.Container(
            col={"xs": 12, "sm": 6, "md": 3},
            content=self._panel(
                ft.Column(
                    controls=[
                        ft.Icon(icon, color="#BDBDBD", size=20),
                        ft.Text(
                            value,
                            size=19,
                            weight=ft.FontWeight.W_600,
                            color=TEXT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(label, size=11, color=MUTED),
                        ft.Text(detail, size=10, color="#66666A")
                        if detail
                        else ft.Container(),
                    ],
                    spacing=8,
                )
            ),
        )

    @property
    def restart_requested(self) -> bool:
        return self._restart_requested

    async def _show_process_confirmation(self, *, restart: bool) -> None:
        if self.page is None:
            return

        action_label = "Restart Bot" if restart else "Matikan Bot"
        explanation = (
            "Senna akan menutup semua subsystem dengan rapi, lalu menjalankan "
            "ulang program."
            if restart
            else "Senna akan menutup semua subsystem dan keluar dari program."
        )

        async def cancel(e: Any) -> None:
            del e
            if self.page is not None:
                self.page.close(dialog)

        async def confirm(e: Any) -> None:
            del e
            if self.page is not None:
                self.page.close(dialog)
            self._restart_requested = restart
            print(
                f"[SENA UI] process action confirmed "
                f"action={'restart' if restart else 'shutdown'}"
            )
            self._shutdown_event.set()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Konfirmasi {action_label}"),
            content=ft.Text(explanation),
            actions=[
                ft.Button("Batal", on_click=cancel),
                ft.Button(
                    action_label,
                    icon=(
                        ft.Icons.RESTART_ALT
                        if restart
                        else ft.Icons.POWER_SETTINGS_NEW
                    ),
                    on_click=confirm,
                ),
            ],
        )
        self.page.open(dialog)

    async def _request_restart(self, e: Any) -> None:
        del e
        await self._show_process_confirmation(restart=True)

    async def _request_shutdown(self, e: Any) -> None:
        del e
        await self._show_process_confirmation(restart=False)

    async def _reset_current_session(self, e: Any) -> None:
        del e
        if self.ctx.assistant is None:
            self.settings_status.value = "AI Assistant tidak aktif."
        elif not self.chat_channel.value:
            self.settings_status.value = "Pilih channel di Terminal Chat terlebih dahulu."
        else:
            guild_id = int(self.chat_guild.value) if self.chat_guild.value else None
            removed = self.ctx.assistant.sessions.clear_channel(
                source="discord_text",
                guild_id=guild_id,
                channel_id=int(self.chat_channel.value),
            )
            self.settings_status.value = (
                f"Session channel direset ({removed} session). Memory jangka panjang tetap aman."
            )
        if self.page is not None:
            self.page.update()

    async def _reset_all_sessions(self, e: Any) -> None:
        del e
        if self.page is None:
            return

        async def cancel(event: Any) -> None:
            del event
            if self.page is not None:
                self.page.close(dialog)

        async def confirm(event: Any) -> None:
            del event
            removed = (
                self.ctx.assistant.sessions.clear()
                if self.ctx.assistant is not None
                else 0
            )
            self.settings_status.value = (
                f"Semua session direset ({removed} session). Memory dan konfigurasi tidak dihapus."
            )
            if self.page is not None:
                self.page.close(dialog)
                self.page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Reset semua chat session?"),
            content=ft.Text(
                "History jangka pendek dan status aktif/diam akan dihapus. "
                "Memory jangka panjang, personality, jadwal, dan settings tetap tersimpan."
            ),
            actions=[
                ft.Button("Batal", on_click=cancel),
                ft.Button("Reset Semua", icon=ft.Icons.DELETE_SWEEP, on_click=confirm),
            ],
        )
        self.page.open(dialog)

    # ---------- dashboard ----------
    def _dashboard(self) -> ft.Control:
        runtime = self.runtime_status
        cards = ft.ResponsiveRow(
            controls=[
                self._card(
                    "Discord bot",
                    str(self.ctx.client.user or "Offline"),
                    ft.Icons.SMART_TOY_OUTLINED,
                    "Gateway connected" if self.ctx.client.is_ready() else "Starting",
                ),
                self._card("Servers", str(len(self.ctx.client.guilds)), ft.Icons.DNS_OUTLINED),
                self._card(
                    "AI",
                    "Enabled" if runtime.ai_enabled else "Disabled",
                    ft.Icons.PSYCHOLOGY_OUTLINED,
                ),
                self._card(
                    "Device",
                    self.device.kind.value,
                    ft.Icons.DEVICES_OUTLINED,
                    self.device.machine,
                ),
            ],
            spacing=12,
            run_spacing=12,
        )
        feature_rows: list[ft.Control] = []
        for result in self.feature_results.values():
            color = (
                SUCCESS
                if result.state is FeatureLoadState.ENABLED
                else WARNING
                if result.state is FeatureLoadState.SKIPPED
                else ERROR
            )
            feature_rows.append(
                ft.Row(
                    controls=[
                        ft.Container(width=8, height=8, border_radius=99, bgcolor=color),
                        ft.Text(
                            f"{result.spec.label} · {result.state.value.upper()} · {result.detail}",
                            color=MUTED,
                            size=11,
                            expand=True,
                        ),
                    ]
                )
            )
        return self._body(
            [
                self._title("Dashboard", "Runtime overview dan health Senna"),
                cards,
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("Core runtime", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.Text(runtime.summary(), color=MUTED, size=11),
                            ft.Text(
                                "Action tools · "
                                + (", ".join(runtime.action_tools) or "none"),
                                color=MUTED,
                                size=11,
                            ),
                        ],
                        spacing=8,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("Feature health", color=TEXT, weight=ft.FontWeight.W_600),
                            *feature_rows,
                        ],
                        spacing=10,
                    )
                ),
            ]
        )

    # ---------- terminal chat ----------
    async def notify_discord_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        channel_name = getattr(message.channel, "name", str(message.channel.id))
        self._chat_lines.append(
            f"{message.author.display_name} · #{channel_name}\n{message.content}"
        )
        self._chat_lines = self._chat_lines[-400:]
        if self.page and self._selected_index == 1:
            self.chat_view.value = "\n\n".join(self._chat_lines)
            self.page.update()

    async def _chat_guild_changed(self, e: Any) -> None:
        del e
        guild = (
            self.ctx.client.get_guild(int(self.chat_guild.value))
            if self.chat_guild.value
            else None
        )
        channels = list(guild.text_channels) if guild else []
        self.chat_channel.options = self._options(
            [(channel.id, f"#{channel.name}") for channel in channels]
        )
        self.chat_channel.value = str(channels[0].id) if channels else None
        if self.page:
            self.page.update()

    async def _send_chat(self, e: Any) -> None:
        del e
        text = (self.chat_input.value or "").strip()
        if not text or not self.chat_channel.value:
            return
        channel = self.ctx.client.get_channel(int(self.chat_channel.value))
        try:
            if not isinstance(channel, discord.TextChannel):
                raise ValueError("Channel tidak valid.")
            await channel.send(text)
            self._chat_lines.append(f"Senna · #{channel.name}\n{text}")
            self.chat_input.value = ""
        except Exception as error:
            self._chat_lines.append(f"SYSTEM\n{type(error).__name__}: {error}")
        self.chat_view.value = "\n\n".join(self._chat_lines[-400:])
        if self.page:
            self.page.update()

    async def _clear_chat(self, e: Any) -> None:
        del e
        self._chat_lines.clear()
        self.chat_view.value = ""
        if self.page:
            self.page.update()

    def _terminal_chat(self) -> ft.Control:
        self.chat_guild.options = self._guild_options()
        if self.chat_guild.value is None and self.ctx.client.guilds:
            guild = self.ctx.client.guilds[0]
            self.chat_guild.value = str(guild.id)
            self.chat_channel.options = self._options(
                [(c.id, f"#{c.name}") for c in guild.text_channels]
            )
            self.chat_channel.value = (
                str(guild.text_channels[0].id) if guild.text_channels else None
            )
        self.chat_view.value = "\n\n".join(self._chat_lines[-400:])
        return self._body(
            [
                self._title("Terminal Chat", "Kirim dan pantau Discord dari control center"),
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(col={"xs": 12, "md": 6}, content=self.chat_guild),
                        ft.Container(col={"xs": 12, "md": 6}, content=self.chat_channel),
                    ],
                    spacing=10,
                    run_spacing=10,
                ),
                ft.Container(
                    height=420 if self._compact else 520,
                    content=self._panel(self.chat_view, expand=True, padding=10),
                ),
                ft.Row(
                    controls=[
                        self.chat_input,
                        ft.IconButton(icon=ft.Icons.SEND_ROUNDED, on_click=self._send_chat),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                            on_click=self._clear_chat,
                        ),
                    ]
                ),
            ]
        )

    # ---------- emoji manager ----------
    def _emoji_selected_guild(self) -> discord.Guild | None:
        return (
            self.ctx.client.get_guild(int(self.emoji_guild.value))
            if self.emoji_guild.value
            else None
        )

    def _refresh_emoji_list(self) -> None:
        guild = self._emoji_selected_guild()
        if guild is None:
            self.emoji_text.value = "Pilih server."
            self.emoji_delete.options = []
            self.emoji_delete.value = None
            return
        emojis = [emoji for emoji in guild.emojis if not emoji.managed]
        self.emoji_text.value = (
            "\n".join(
                f"{emoji.name} · id={emoji.id} · {'animated' if emoji.animated else 'static'}"
                for emoji in emojis
            )
            or "Belum ada custom emoji."
        )
        self.emoji_delete.options = self._options(
            [(emoji.id, emoji.name) for emoji in emojis]
        )
        valid_ids = {str(emoji.id) for emoji in emojis}
        if self.emoji_delete.value not in valid_ids:
            self.emoji_delete.value = str(emojis[0].id) if emojis else None

    async def _emoji_guild_changed(self, e: Any) -> None:
        del e
        self._refresh_emoji_list()
        if self.page:
            self.page.update()

    async def _refresh_emoji(self, e: Any) -> None:
        await self._emoji_guild_changed(e)

    def _emoji_name_for_path(
        self, path: Path, existing: set[str], requested: str = ""
    ) -> str:
        base = requested.strip() or path.stem
        base = re.sub(r"[^A-Za-z0-9_]", "_", base).strip("_") or "emoji"
        base = base[:28]
        if len(base) < 2:
            base = f"emoji_{base}"
        candidate = base
        number = 2
        while candidate in existing:
            suffix = f"_{number}"
            candidate = (base[: 32 - len(suffix)] + suffix)[:32]
            number += 1
        return candidate

    async def _create_emoji_from_path(
        self,
        guild: discord.Guild,
        path: Path,
        existing: set[str],
        requested_name: str = "",
    ) -> discord.Emoji:
        if not path.is_file():
            raise FileNotFoundError(f"File tidak ditemukan: {path}")
        if path.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            raise ValueError("Format emoji harus PNG/JPG/GIF/WEBP.")
        if path.stat().st_size > MAX_EMOJI_SIZE:
            raise ValueError(
                f"{path.name} terlalu besar: {path.stat().st_size / 1024:.1f} KB; "
                f"maks {MAX_EMOJI_SIZE / 1024:.0f} KB."
            )
        name = self._emoji_name_for_path(path, existing, requested_name)
        emoji = await guild.create_custom_emoji(
            name=name,
            image=path.read_bytes(),
            reason="Senna Flet emoji manager",
        )
        existing.add(emoji.name)
        return emoji

    async def _emoji_upload_file(self, e: Any) -> None:
        del e
        guild = self._emoji_selected_guild()
        if guild is None:
            self.emoji_status.value = "Pilih server dulu."
            self.emoji_status.color = ERROR
        else:
            try:
                path = Path((self.emoji_path.value or "").strip()).expanduser()
                existing = {emoji.name for emoji in guild.emojis}
                emoji = await self._create_emoji_from_path(
                    guild,
                    path,
                    existing,
                    self.emoji_name.value or "",
                )
                self.emoji_status.value = f"Ditambahkan: {emoji.name}"
                self.emoji_status.color = SUCCESS
                self._refresh_emoji_list()
            except Exception as error:
                self.emoji_status.value = f"Upload gagal · {type(error).__name__}: {error}"
                self.emoji_status.color = ERROR
        if self.page:
            self.page.update()

    async def _emoji_upload_folder(self, e: Any) -> None:
        del e
        guild = self._emoji_selected_guild()
        if guild is None:
            self.emoji_status.value = "Pilih server dulu."
            self.emoji_status.color = ERROR
        else:
            try:
                folder = Path((self.emoji_path.value or "").strip()).expanduser()
                if not folder.is_dir():
                    raise NotADirectoryError(f"Folder tidak ditemukan: {folder}")
                files = sorted(
                    path
                    for path in folder.iterdir()
                    if path.is_file()
                    and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}
                )
                existing = {emoji.name for emoji in guild.emojis}
                success = 0
                skipped = 0
                for path in files:
                    if path.stat().st_size > MAX_EMOJI_SIZE:
                        skipped += 1
                        continue
                    try:
                        await self._create_emoji_from_path(guild, path, existing)
                        success += 1
                    except discord.HTTPException:
                        skipped += 1
                self.emoji_status.value = (
                    f"Bulk selesai · berhasil={success} skip/gagal={skipped}"
                )
                self.emoji_status.color = SUCCESS if success else WARNING
                self._refresh_emoji_list()
            except Exception as error:
                self.emoji_status.value = f"Bulk gagal · {type(error).__name__}: {error}"
                self.emoji_status.color = ERROR
        if self.page:
            self.page.update()

    async def _emoji_delete_selected(self, e: Any) -> None:
        del e
        guild = self._emoji_selected_guild()
        if guild is None or not self.emoji_delete.value:
            self.emoji_status.value = "Pilih server dan emoji dulu."
            self.emoji_status.color = ERROR
        else:
            try:
                emoji_id = int(self.emoji_delete.value)
                emoji = next(
                    (item for item in guild.emojis if item.id == emoji_id), None
                )
                if emoji is None or emoji.managed:
                    raise LookupError("Emoji tidak ditemukan atau managed.")
                name = emoji.name
                await guild.delete_emoji(emoji, reason="Senna Flet emoji manager")
                self.emoji_status.value = f"Dihapus: {name}"
                self.emoji_status.color = SUCCESS
                self._refresh_emoji_list()
            except Exception as error:
                self.emoji_status.value = f"Hapus gagal · {type(error).__name__}: {error}"
                self.emoji_status.color = ERROR
        if self.page:
            self.page.update()

    def _emoji(self) -> ft.Control:
        self.emoji_guild.options = self._guild_options()
        if self.emoji_guild.value is None and self.ctx.client.guilds:
            self.emoji_guild.value = str(self.ctx.client.guilds[0].id)
        self._refresh_emoji_list()
        return self._body(
            [
                self._title("Emoji", "Tambah, bulk upload, lihat, dan hapus custom emoji"),
                self._panel(
                    ft.Column(
                        controls=[
                            self.emoji_guild,
                            self.emoji_path,
                            self.emoji_name,
                            ft.Row(
                                wrap=True,
                                controls=[
                                    ft.Button(
                                        "Upload file",
                                        icon=ft.Icons.UPLOAD_FILE,
                                        on_click=self._emoji_upload_file,
                                    ),
                                    ft.Button(
                                        "Upload folder",
                                        icon=ft.Icons.DRIVE_FOLDER_UPLOAD_OUTLINED,
                                        on_click=self._emoji_upload_folder,
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.REFRESH,
                                        on_click=self._refresh_emoji,
                                    ),
                                ],
                            ),
                            ft.Text(
                                f"Maksimum per emoji: {MAX_EMOJI_SIZE / 1024:.0f} KB. Path adalah path di device yang menjalankan Sena.",
                                color=MUTED,
                                size=10,
                            ),
                            self.emoji_status,
                        ],
                        spacing=12,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            self.emoji_delete,
                            ft.Button(
                                "Delete selected",
                                icon=ft.Icons.DELETE_OUTLINE,
                                on_click=self._emoji_delete_selected,
                            ),
                        ],
                        spacing=10,
                    )
                ),
                ft.Container(
                    height=360 if self._compact else 460,
                    content=self._panel(
                        ft.Column(
                            controls=[self.emoji_text],
                            scroll=ft.ScrollMode.AUTO,
                            expand=True,
                        ),
                        expand=True,
                        padding=12,
                    ),
                ),
            ]
        )

    # ---------- voice ----------
    def _initial_voice_preferences(self) -> VoicePreferences:
        return VoicePreferences(
            provider_name=TTS_PROVIDER,
            language=TTS_LANGUAGE,
            converter=VoiceConverterSettings(
                enabled=VOICE_CONVERTER_ENABLED,
                converter=VOICE_CONVERTER,
                model=None,
                pitch=VOICE_CONVERTER_PITCH,
                index_ratio=VOICE_CONVERTER_INDEX_RATIO,
                protect=VOICE_CONVERTER_PROTECT,
            ),
        )

    def _load_voice_preferences_safe(self) -> VoicePreferences:
        try:
            return load_preferences(VOICE_SETTINGS_FILE, self._initial_voice_preferences())
        except Exception as error:
            print(f"[SENA UI VOICE] settings load failed: {type(error).__name__}: {error}")
            return self._initial_voice_preferences()

    async def _voice_guild_changed(self, e: Any) -> None:
        del e
        guild = (
            self.ctx.client.get_guild(int(self.voice_guild.value))
            if self.voice_guild.value
            else None
        )
        channels = list(guild.voice_channels) if guild else []
        self.voice_channel.options = self._options(
            [(channel.id, channel.name) for channel in channels]
        )
        self.voice_channel.value = str(channels[0].id) if channels else None
        if self.page:
            self.page.update()

    async def _voice_join(self, e: Any) -> None:
        del e
        if not self.voice_channel.value:
            self.voice_status.value = "Pilih VC dulu."
            self.voice_status.color = ERROR
        else:
            channel = self.ctx.client.get_channel(int(self.voice_channel.value))
            try:
                if not isinstance(channel, discord.VoiceChannel):
                    raise ValueError("Voice channel tidak valid.")
                voice = channel.guild.voice_client
                if voice and voice.is_connected():
                    if voice.channel is None or voice.channel.id != channel.id:
                        await voice.move_to(channel)
                else:
                    await channel.connect()
                self.voice_status.value = f"Connected · {channel.name}"
                self.voice_status.color = SUCCESS
            except Exception as error:
                self.voice_status.value = (
                    f"Join gagal · {type(error).__name__}: {error}"
                )
                self.voice_status.color = ERROR
                print(f"[SENA UI VOICE] join failed: {type(error).__name__}: {error}")
        if self.page:
            self.page.update()

    async def _voice_leave(self, e: Any) -> None:
        del e
        guild = (
            self.ctx.client.get_guild(int(self.voice_guild.value))
            if self.voice_guild.value
            else None
        )
        try:
            if guild and guild.voice_client:
                await guild.voice_client.disconnect(force=False)
            self.voice_status.value = "Disconnected"
            self.voice_status.color = MUTED
        except Exception as error:
            self.voice_status.value = f"Leave gagal · {type(error).__name__}: {error}"
            self.voice_status.color = ERROR
        if self.page:
            self.page.update()

    async def _save_voice_settings(self, e: Any) -> None:
        del e
        try:
            prefs = VoicePreferences(
                provider_name=str(self.tts_provider.value),
                language=(self.tts_language.value or "").strip().lower(),
                converter=VoiceConverterSettings(
                    enabled=bool(self.converter_enabled.value),
                    converter=str(self.converter_name.value),
                    model=(self.converter_model.value or "").strip() or None,
                    pitch=int(self.converter_pitch.value or "0"),
                    index_ratio=float(self.converter_index.value or "0"),
                    protect=float(self.converter_protect.value or "0"),
                ),
            )
            if not prefs.language:
                raise ValueError("Bahasa TTS tidak boleh kosong.")
            save_preferences(VOICE_SETTINGS_FILE, prefs)

            current_stt = load_configured_settings()
            stt = replace(
                current_stt,
                enabled=bool(self.stt_enabled.value),
                model=(self.stt_model.value or "").strip(),
                language=(self.stt_language.value or "").strip(),
                vad_enabled=bool(self.stt_vad.value),
                min_speech_seconds=float(self.stt_min_speech.value or "0"),
                end_silence_seconds=float(self.stt_end_silence.value or "0"),
                max_utterance_seconds=float(self.stt_max_utterance.value or "0"),
                vad_rms_threshold=int(self.stt_rms.value or "0"),
                voice_session_timeout_seconds=float(self.stt_session_timeout.value or "0"),
                wake_words=tuple(
                    item.strip().casefold()
                    for item in (self.stt_wake_words.value or "").split(",")
                    if item.strip()
                ),
                queue_size=int(self.stt_queue.value or "0"),
                workers=int(self.stt_workers.value or "0"),
                log_transcript=bool(self.stt_log_transcript.value),
                listen_mode=str(self.stt_listen_mode.value),
                save_audio=False,
            )
            save_stt_settings(STT_SETTINGS_FILE, stt)
            self.voice_save_status.value = "Voice + STT settings disimpan."
            self.voice_save_status.color = SUCCESS
        except Exception as error:
            self.voice_save_status.value = (
                f"Save gagal · {type(error).__name__}: {error}"
            )
            self.voice_save_status.color = ERROR
        if self.page:
            self.page.update()

    def _voice_manager_from_form(self) -> VoiceManager:
        language = (self.tts_language.value or "").strip().lower()
        if not language:
            raise ValueError("Bahasa TTS tidak boleh kosong.")
        return VoiceManager(
            provider_name=str(self.tts_provider.value or "gtts"),
            language=language,
            converter_settings=VoiceConverterSettings(
                enabled=bool(self.converter_enabled.value),
                converter=str(self.converter_name.value or "passthrough"),
                model=(self.converter_model.value or "").strip() or None,
                pitch=int(self.converter_pitch.value or "0"),
                index_ratio=float(self.converter_index.value or "0"),
                protect=float(self.converter_protect.value or "0"),
            ),
            settings_file=VOICE_SETTINGS_FILE,
        )

    async def _generate_test_tts(self, e: Any) -> None:
        del e
        manager: VoiceManager | None = None
        try:
            text = (self.tts_test_text.value or "").strip()
            if not text:
                raise ValueError("Masukkan teks test TTS.")
            self.tts_test_status.value = "Generating MP3..."
            self.tts_test_status.color = WARNING
            if self.page:
                self.page.update()
            manager = self._voice_manager_from_form()
            output = await manager.generate_test(text)
            self.tts_test_status.value = f"TTS READY · MP3: {output.resolve()}"
            self.tts_test_status.color = SUCCESS
        except Exception as error:
            self.tts_test_status.value = (
                f"TTS gagal · {type(error).__name__}: {error}"
            )
            self.tts_test_status.color = ERROR
            print(f"[SENA UI TTS] generate failed: {type(error).__name__}: {error}")
        finally:
            if manager is not None:
                await manager.close()
        if self.page:
            self.page.update()

    async def _speak_tts_in_vc(self, e: Any) -> None:
        del e
        manager: VoiceManager | None = None
        try:
            text = (self.tts_test_text.value or "").strip()
            if not text:
                raise ValueError("Masukkan teks yang akan diucapkan.")
            guild = (
                self.ctx.client.get_guild(int(self.voice_guild.value))
                if self.voice_guild.value
                else None
            )
            voice_client = guild.voice_client if guild else None
            if voice_client is None or not voice_client.is_connected():
                raise RuntimeError("Bot belum terhubung ke VC. Tekan Join dulu.")
            self.tts_test_status.value = "Generating dan mengirim audio ke VC..."
            self.tts_test_status.color = WARNING
            if self.page:
                self.page.update()
            manager = self._voice_manager_from_form()
            await manager.speak(voice_client, text)
            self.tts_test_status.value = "VOICE TX READY · audio selesai diputar."
            self.tts_test_status.color = SUCCESS
        except Exception as error:
            self.tts_test_status.value = (
                f"Speak gagal · {type(error).__name__}: {error}"
            )
            self.tts_test_status.color = ERROR
            print(f"[SENA UI TTS] speak failed: {type(error).__name__}: {error}")
        finally:
            if manager is not None:
                await manager.close()
        if self.page:
            self.page.update()

    def _voice(self) -> ft.Control:
        self.voice_guild.options = self._guild_options()
        if self.voice_guild.value is None and self.ctx.client.guilds:
            guild = self.ctx.client.guilds[0]
            self.voice_guild.value = str(guild.id)
            self.voice_channel.options = self._options(
                [(channel.id, channel.name) for channel in guild.voice_channels]
            )
            self.voice_channel.value = (
                str(guild.voice_channels[0].id) if guild.voice_channels else None
            )

        prefs = self._load_voice_preferences_safe()
        stt = load_configured_settings()
        voice_feature = self.feature_results.get("voice")
        backend_ok = bool(voice_feature and voice_feature.available)
        backend_detail = voice_feature.detail if voice_feature else "not registered"

        self.tts_provider = ft.Dropdown(
            label="TTS Provider",
            value=prefs.provider_name,
            options=self._options([(name, name) for name in PROVIDERS]),
        )
        self.tts_language = ft.TextField(
            label="TTS Language", value=prefs.language, border_color=BORDER
        )
        self.tts_test_text = ft.TextField(
            label="Teks Generate/Test",
            value="Halo, ini adalah tes suara Sena.",
            multiline=True,
            min_lines=2,
            max_lines=4,
            border_color=BORDER,
        )
        self.converter_enabled = ft.Switch(
            label="Enable voice converter", value=prefs.converter.enabled
        )
        self.converter_name = ft.Dropdown(
            label="Converter",
            value=prefs.converter.converter,
            options=self._options([(name, name) for name in CONVERTERS]),
        )
        self.converter_model = ft.TextField(
            label="Converter model/slot",
            value=prefs.converter.model or "",
            border_color=BORDER,
        )
        self.converter_pitch = ft.TextField(
            label="Pitch (-24..24)",
            value=str(prefs.converter.pitch),
            border_color=BORDER,
        )
        self.converter_index = ft.TextField(
            label="Index ratio (0..1)",
            value=str(prefs.converter.index_ratio),
            border_color=BORDER,
        )
        self.converter_protect = ft.TextField(
            label="Protect (0..1)",
            value=str(prefs.converter.protect),
            border_color=BORDER,
        )

        self.stt_enabled = ft.Switch(label="Enable STT", value=stt.enabled)
        self.stt_model = ft.TextField(label="STT model", value=stt.model, border_color=BORDER)
        self.stt_language = ft.TextField(
            label="STT language", value=stt.language, border_color=BORDER
        )
        self.stt_vad = ft.Switch(label="Enable VAD", value=stt.vad_enabled)
        self.stt_min_speech = ft.TextField(
            label="Min speech (s)", value=str(stt.min_speech_seconds), border_color=BORDER
        )
        self.stt_end_silence = ft.TextField(
            label="End silence (s)", value=str(stt.end_silence_seconds), border_color=BORDER
        )
        self.stt_max_utterance = ft.TextField(
            label="Max utterance (s)", value=str(stt.max_utterance_seconds), border_color=BORDER
        )
        self.stt_rms = ft.TextField(
            label="VAD RMS threshold", value=str(stt.vad_rms_threshold), border_color=BORDER
        )
        self.stt_session_timeout = ft.TextField(
            label="Voice session timeout (s)",
            value=str(stt.voice_session_timeout_seconds),
            border_color=BORDER,
        )
        self.stt_wake_words = ft.TextField(
            label="Wake words (pisahkan koma)",
            value=", ".join(stt.wake_words),
            border_color=BORDER,
        )
        self.stt_queue = ft.TextField(
            label="STT queue size", value=str(stt.queue_size), border_color=BORDER
        )
        self.stt_workers = ft.TextField(
            label="STT workers", value=str(stt.workers), border_color=BORDER
        )
        self.stt_log_transcript = ft.Switch(
            label="Log transcript", value=stt.log_transcript
        )
        self.stt_listen_mode = ft.Dropdown(
            label="Listen mode",
            value=stt.listen_mode,
            options=self._options(
                [
                    ("wake_word", "wake_word"),
                    ("always_active", "always_active"),
                    ("test_only", "test_only"),
                ]
            ),
        )

        return self._body(
            [
                self._title("Voice", "VC transport, TTS, STT, converter, dan music foundation"),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text(
                                "Voice backend ready" if backend_ok else "Voice backend degraded",
                                color=SUCCESS if backend_ok else ERROR,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(backend_detail, color=MUTED, size=11),
                            ft.Text(
                                "Settings tetap bisa diedit walau runtime voice dependency belum lengkap.",
                                color=MUTED,
                                size=10,
                            ),
                        ],
                        spacing=5,
                    )
                ),
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(col={"xs": 12, "md": 6}, content=self.voice_guild),
                        ft.Container(col={"xs": 12, "md": 6}, content=self.voice_channel),
                    ]
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            self.voice_status,
                            ft.Row(
                                wrap=True,
                                controls=[
                                    ft.Button("Join", icon=ft.Icons.CALL, on_click=self._voice_join),
                                    ft.Button(
                                        "Leave", icon=ft.Icons.CALL_END, on_click=self._voice_leave
                                    ),
                                ],
                            ),
                        ]
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("TTS", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.tts_provider),
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.tts_language),
                                ]
                            ),
                            self.tts_test_text,
                            ft.Row(
                                wrap=True,
                                controls=[
                                    ft.Button(
                                        "Generate/Test TTS",
                                        icon=ft.Icons.AUDIO_FILE_OUTLINED,
                                        on_click=self._generate_test_tts,
                                    ),
                                    ft.Button(
                                        "Speak in VC",
                                        icon=ft.Icons.RECORD_VOICE_OVER_OUTLINED,
                                        on_click=self._speak_tts_in_vc,
                                    ),
                                ],
                            ),
                            self.tts_test_status,
                            ft.Divider(color=BORDER),
                            ft.Text("Voice Converter", color=TEXT, weight=ft.FontWeight.W_600),
                            self.converter_enabled,
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.converter_name),
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.converter_model),
                                    ft.Container(col={"xs": 12, "md": 4}, content=self.converter_pitch),
                                    ft.Container(col={"xs": 12, "md": 4}, content=self.converter_index),
                                    ft.Container(col={"xs": 12, "md": 4}, content=self.converter_protect),
                                ]
                            ),
                        ],
                        spacing=12,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("STT", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.Row(wrap=True, controls=[self.stt_enabled, self.stt_vad, self.stt_log_transcript]),
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.stt_model),
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.stt_language),
                                    ft.Container(col={"xs": 12, "md": 4}, content=self.stt_min_speech),
                                    ft.Container(col={"xs": 12, "md": 4}, content=self.stt_end_silence),
                                    ft.Container(col={"xs": 12, "md": 4}, content=self.stt_max_utterance),
                                    ft.Container(col={"xs": 12, "md": 4}, content=self.stt_rms),
                                    ft.Container(col={"xs": 12, "md": 4}, content=self.stt_queue),
                                    ft.Container(col={"xs": 12, "md": 4}, content=self.stt_workers),
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.stt_session_timeout),
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.stt_listen_mode),
                                    ft.Container(col=12, content=self.stt_wake_words),
                                ]
                            ),
                            ft.Button(
                                "Save voice settings",
                                icon=ft.Icons.SAVE_OUTLINED,
                                on_click=self._save_voice_settings,
                            ),
                            self.voice_save_status,
                        ],
                        spacing=12,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("Music", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.Text(
                                "Player/queue akan menggunakan voice transport yang sama. Action API music.play dapat ditambahkan tanpa mengubah layout voice ini.",
                                color=MUTED,
                                size=11,
                            ),
                        ]
                    )
                ),
            ]
        )

    # ---------- AI + audience personality ----------
    async def _apply_ai_settings(self, e: Any) -> None:
        del e
        manager = self.ctx.assistant
        if manager is None:
            self.ai_status.value = "AI Assistant tidak aktif."
            self.ai_status.color = ERROR
        else:
            try:
                settings = replace(
                    manager.settings,
                    provider_name=str(self.ai_provider.value),
                    openrouter_model=(self.ai_openrouter.value or "").strip(),
                    nvidia_nim_model=(self.ai_nvidia.value or "").strip(),
                    nvidia_nim_base_url=(self.ai_nvidia_base.value or "").strip(),
                    max_tokens=int(self.ai_tokens.value or "0"),
                    request_timeout_seconds=float(self.ai_timeout.value or "0"),
                    retry_count=int(self.ai_retry_count.value or "0"),
                    retry_delay_seconds=float(self.ai_retry_delay.value or "0"),
                    chat_timeout_seconds=float(self.ai_chat_timeout.value or "0"),
                    history_max_messages=int(self.ai_history.value or "0"),
                    routing_enabled=bool(self.ai_routing_enabled.value),
                    fast_provider=str(self.ai_fast_provider.value or "primary"),
                    fast_model=(self.ai_fast_model.value or "").strip(),
                    standard_provider=str(
                        self.ai_standard_provider.value or "primary"
                    ),
                    standard_model=(self.ai_standard_model.value or "").strip(),
                    complex_provider=str(
                        self.ai_complex_provider.value or "nvidia_nim"
                    ),
                    complex_model=(self.ai_complex_model.value or "").strip(),
                    fallback_provider=str(
                        self.ai_fallback_provider.value or "openrouter"
                    ),
                    fallback_model=(self.ai_fallback_model.value or "").strip(),
                    json_prefill_enabled=bool(self.ai_json_prefill.value),
                    prompt_cache_enabled=bool(self.ai_prompt_cache.value),
                )
                await manager.apply_settings(settings)
                save_ai_settings(AI_SETTINGS_FILE, settings)
                self.ai_status.value = "AI settings applied & saved."
                self.ai_status.color = SUCCESS
            except Exception as error:
                self.ai_status.value = f"Apply gagal · {type(error).__name__}: {error}"
                self.ai_status.color = ERROR
        if self.page:
            self.page.update()

    async def _reset_routing_defaults(self, e: Any) -> None:
        del e
        self.ai_routing_enabled.value = True
        self.ai_fast_provider.value = "primary"
        self.ai_fast_model.value = ""
        self.ai_standard_provider.value = "primary"
        self.ai_standard_model.value = ""
        self.ai_complex_provider.value = "nvidia_nim"
        self.ai_complex_model.value = "moonshotai/kimi-k3"
        self.ai_fallback_provider.value = "openrouter"
        self.ai_fallback_model.value = "openai/gpt-4o-mini"
        self.ai_json_prefill.value = True
        self.ai_prompt_cache.value = True
        self.ai_status.value = (
            "Default routing dimuat. Tekan Apply AI settings untuk menyimpan."
        )
        self.ai_status.color = WARNING
        if self.page:
            self.page.update()

    async def _save_personality(self, e: Any) -> None:
        del e
        manager = self.ctx.assistant
        if manager is None or not hasattr(manager, "audience_personality"):
            self.personality_status.value = "Audience personality manager belum aktif."
            self.personality_status.color = ERROR
        else:
            try:
                current = manager.audience_personality.config
                owner = replace(
                    current.owner,
                    preferred_address=(self.owner_address.value or "").strip(),
                    relationship=(self.owner_relationship.value or "").strip(),
                    tone=(self.owner_tone.value or "").strip(),
                    teasing=int(self.owner_teasing.value or "0"),
                    affection=int(self.owner_affection.value or "0"),
                    respect=int(self.owner_respect.value or "0"),
                    roughness=int(self.owner_roughness.value or "0"),
                )
                user = replace(
                    current.user,
                    relationship=(self.user_relationship.value or "").strip(),
                    tone=(self.user_tone.value or "").strip(),
                    teasing=int(self.user_teasing.value or "0"),
                    affection=int(self.user_affection.value or "0"),
                    respect=int(self.user_respect.value or "0"),
                    roughness=int(self.user_roughness.value or "0"),
                )
                manager.audience_personality.update(
                    AudiencePersonalityConfig(owner=owner, user=user)
                )
                self.personality_status.value = "Owner/user personality disimpan dan aktif."
                self.personality_status.color = SUCCESS
            except Exception as error:
                self.personality_status.value = (
                    f"Personality gagal · {type(error).__name__}: {error}"
                )
                self.personality_status.color = ERROR
        if self.page:
            self.page.update()

    def _ai_settings(self) -> ft.Control:
        manager = self.ctx.assistant
        settings = manager.settings if manager else None
        self.ai_provider = ft.Dropdown(
            label="Provider",
            value=settings.provider_name if settings else "openrouter",
            options=self._options(
                [("openrouter", "OpenRouter"), ("nvidia_nim", "NVIDIA NIM")]
            ),
        )
        self.ai_nvidia = ft.TextField(
            label="NVIDIA NIM model",
            value=settings.nvidia_nim_model if settings else "",
            border_color=BORDER,
        )
        self.ai_nvidia_base = ft.TextField(
            label="NVIDIA NIM base URL",
            value=settings.nvidia_nim_base_url if settings else "",
            border_color=BORDER,
        )
        self.ai_openrouter = ft.TextField(
            label="OpenRouter model",
            value=settings.openrouter_model if settings else "",
            border_color=BORDER,
        )
        self.ai_tokens = ft.TextField(
            label="Max tokens",
            value=str(settings.max_tokens if settings else 300),
            border_color=BORDER,
        )
        self.ai_timeout = ft.TextField(
            label="Request timeout (s)",
            value=str(settings.request_timeout_seconds if settings else 60),
            border_color=BORDER,
        )
        self.ai_retry_count = ft.TextField(
            label="Retry count",
            value=str(settings.retry_count if settings else 2),
            border_color=BORDER,
        )
        self.ai_retry_delay = ft.TextField(
            label="Retry delay (s)",
            value=str(settings.retry_delay_seconds if settings else 1),
            border_color=BORDER,
        )
        self.ai_chat_timeout = ft.TextField(
            label="Session timeout (s)",
            value=str(settings.chat_timeout_seconds if settings else 120),
            border_color=BORDER,
        )
        self.ai_history = ft.TextField(
            label="History max messages",
            value=str(settings.history_max_messages if settings else 20),
            border_color=BORDER,
        )
        route_provider_items = [
            ("primary", "Ikuti Primary"),
            ("nvidia_nim", "NVIDIA NIM"),
            ("openrouter", "OpenRouter"),
        ]
        self.ai_routing_enabled = ft.Switch(
            label="Enable tiered routing",
            value=settings.routing_enabled if settings else True,
        )
        self.ai_json_prefill = ft.Switch(
            label="JSON assistant prefill",
            value=settings.json_prefill_enabled if settings else True,
        )
        self.ai_prompt_cache = ft.Switch(
            label="Prompt cache",
            value=settings.prompt_cache_enabled if settings else True,
        )
        self.ai_fast_provider = ft.Dropdown(
            label="FAST provider",
            value=settings.fast_provider if settings else "primary",
            options=self._options(route_provider_items),
        )
        self.ai_fast_model = ft.TextField(
            label="FAST model (kosong = model provider/primary)",
            value=settings.fast_model if settings else "",
            border_color=BORDER,
        )
        self.ai_standard_provider = ft.Dropdown(
            label="STANDARD provider",
            value=settings.standard_provider if settings else "primary",
            options=self._options(route_provider_items),
        )
        self.ai_standard_model = ft.TextField(
            label="STANDARD model (kosong = model provider/primary)",
            value=settings.standard_model if settings else "",
            border_color=BORDER,
        )
        self.ai_complex_provider = ft.Dropdown(
            label="COMPLEX provider",
            value=settings.complex_provider if settings else "nvidia_nim",
            options=self._options(route_provider_items),
        )
        self.ai_complex_model = ft.TextField(
            label="COMPLEX model",
            value=settings.complex_model if settings else "moonshotai/kimi-k3",
            border_color=BORDER,
        )
        self.ai_fallback_provider = ft.Dropdown(
            label="Fallback provider",
            value=settings.fallback_provider if settings else "openrouter",
            options=self._options(route_provider_items),
        )
        self.ai_fallback_model = ft.TextField(
            label="Fallback model",
            value=(
                settings.fallback_model
                if settings
                else "openai/gpt-4o-mini"
            ),
            border_color=BORDER,
        )

        audience = (
            manager.audience_personality.config
            if manager is not None and hasattr(manager, "audience_personality")
            else None
        )
        owner = audience.owner if audience else None
        user = audience.user if audience else None
        self.owner_address = ft.TextField(
            label="Owner direct address",
            value=owner.preferred_address if owner else "boss",
            border_color=BORDER,
        )
        self.owner_relationship = ft.TextField(
            label="Owner relationship",
            value=owner.relationship if owner else "father/daughter",
            border_color=BORDER,
        )
        self.owner_tone = ft.TextField(
            label="Owner tone",
            value=owner.tone if owner else "warm, loyal, protective and respectful",
            border_color=BORDER,
        )
        self.owner_teasing = ft.TextField(label="Owner teasing 0-10", value=str(owner.teasing if owner else 3), border_color=BORDER)
        self.owner_affection = ft.TextField(label="Owner affection 0-10", value=str(owner.affection if owner else 8), border_color=BORDER)
        self.owner_respect = ft.TextField(label="Owner respect 0-10", value=str(owner.respect if owner else 10), border_color=BORDER)
        self.owner_roughness = ft.TextField(label="Owner roughness 0-10", value=str(owner.roughness if owner else 1), border_color=BORDER)
        self.user_relationship = ft.TextField(
            label="Normal user relationship",
            value=user.relationship if user else "community user",
            border_color=BORDER,
        )
        self.user_tone = ft.TextField(
            label="Normal user tone",
            value=user.tone if user else "casual, helpful and lightly teasing",
            border_color=BORDER,
        )
        self.user_teasing = ft.TextField(label="User teasing 0-10", value=str(user.teasing if user else 5), border_color=BORDER)
        self.user_affection = ft.TextField(label="User affection 0-10", value=str(user.affection if user else 3), border_color=BORDER)
        self.user_respect = ft.TextField(label="User respect 0-10", value=str(user.respect if user else 7), border_color=BORDER)
        self.user_roughness = ft.TextField(label="User roughness 0-10", value=str(user.roughness if user else 4), border_color=BORDER)

        return self._body(
            [
                self._title("AI Setting", "Provider, inference, session, dan audience personality"),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("LLM", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.ai_provider),
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.ai_tokens),
                                    ft.Container(col=12, content=self.ai_nvidia),
                                    ft.Container(col=12, content=self.ai_nvidia_base),
                                    ft.Container(col=12, content=self.ai_openrouter),
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.ai_timeout),
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.ai_chat_timeout),
                                    ft.Container(col={"xs": 12, "md": 4}, content=self.ai_retry_count),
                                    ft.Container(col={"xs": 12, "md": 4}, content=self.ai_retry_delay),
                                    ft.Container(col={"xs": 12, "md": 4}, content=self.ai_history),
                                ]
                            ),
                            ft.Button("Apply AI settings", icon=ft.Icons.SAVE_OUTLINED, on_click=self._apply_ai_settings),
                            self.ai_status,
                        ],
                        spacing=12,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text(
                                "Model Routing",
                                color=TEXT,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                "FAST untuk respons ringan, STANDARD untuk chat normal, "
                                "COMPLEX untuk coding/analisis. FAST/ STANDARD memakai "
                                "fallback ringan agar tidak nyasar ke NVIDIA/Kimi yang lambat.",
                                color=MUTED,
                                size=11,
                            ),
                            ft.Row(
                                wrap=True,
                                controls=[
                                    self.ai_routing_enabled,
                                    self.ai_json_prefill,
                                    self.ai_prompt_cache,
                                ],
                            ),
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(
                                        col={"xs": 12, "md": 4},
                                        content=self.ai_fast_provider,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 8},
                                        content=self.ai_fast_model,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 4},
                                        content=self.ai_standard_provider,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 8},
                                        content=self.ai_standard_model,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 4},
                                        content=self.ai_complex_provider,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 8},
                                        content=self.ai_complex_model,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 4},
                                        content=self.ai_fallback_provider,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 8},
                                        content=self.ai_fallback_model,
                                    ),
                                ],
                                spacing=10,
                                run_spacing=10,
                            ),
                            ft.Text(
                                "Model kosong hanya diperbolehkan saat provider = Ikuti Primary.",
                                color=MUTED,
                                size=10,
                            ),
                            ft.Row(
                                wrap=True,
                                controls=[
                                    ft.Button(
                                        "Apply AI settings",
                                        icon=ft.Icons.SAVE_OUTLINED,
                                        on_click=self._apply_ai_settings,
                                    ),
                                    ft.Button(
                                        "Reset routing defaults",
                                        icon=ft.Icons.RESTORE,
                                        on_click=self._reset_routing_defaults,
                                    ),
                                ],
                            ),
                        ],
                        spacing=12,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("Owner personality", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.Text(
                                "Dipakai hanya untuk Discord ID owner yang terautentikasi.",
                                color=MUTED,
                                size=10,
                            ),
                            self.owner_address,
                            self.owner_relationship,
                            self.owner_tone,
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(col={"xs": 6, "md": 3}, content=self.owner_teasing),
                                    ft.Container(col={"xs": 6, "md": 3}, content=self.owner_affection),
                                    ft.Container(col={"xs": 6, "md": 3}, content=self.owner_respect),
                                    ft.Container(col={"xs": 6, "md": 3}, content=self.owner_roughness),
                                ]
                            ),
                            ft.Divider(color=BORDER),
                            ft.Text("Normal user personality", color=TEXT, weight=ft.FontWeight.W_600),
                            self.user_relationship,
                            self.user_tone,
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(col={"xs": 6, "md": 3}, content=self.user_teasing),
                                    ft.Container(col={"xs": 6, "md": 3}, content=self.user_affection),
                                    ft.Container(col={"xs": 6, "md": 3}, content=self.user_respect),
                                    ft.Container(col={"xs": 6, "md": 3}, content=self.user_roughness),
                                ]
                            ),
                            ft.Button(
                                "Save owner/user personality",
                                icon=ft.Icons.PERSON_OUTLINE,
                                on_click=self._save_personality,
                            ),
                            self.personality_status,
                        ],
                        spacing=12,
                    )
                ),
            ]
        )

    # ---------- settings/logs ----------
    async def _refresh_logs(self, e: Any = None) -> None:
        del e
        lines = RUNTIME_LOGS.snapshot()
        self.log_text.value = "\n".join(lines) or "Belum ada runtime log."
        if self.page:
            self.page.update()

    async def _clear_logs(self, e: Any) -> None:
        del e
        RUNTIME_LOGS.clear()
        await self._refresh_logs()

    async def _log_pump(self) -> None:
        while self.page is not None:
            if self._selected_index == 5:
                await self._refresh_logs()
            await asyncio.sleep(0.8)

    def _settings(self) -> ft.Control:
        lines = RUNTIME_LOGS.snapshot()
        self.log_text.value = "\n".join(lines) or "Belum ada runtime log."
        web = (
            f"{WEB_HOST}:{WEB_PORT} · local http://127.0.0.1:{WEB_PORT}"
            if self.device.is_android
            else "Desktop Flet app"
        )
        log_box = ft.Container(
            height=500 if self._compact else 620,
            bgcolor="#080808",
            border=ft.Border.all(1, BORDER),
            border_radius=14,
            padding=14,
            content=self.log_scroll,
        )
        return self._body(
            [
                self._title("Settings", "Runtime, network, feature health, dan logs"),
                self._panel(
                    ft.Row(
                        controls=[
                            ft.Text("Live runtime logs", color=TEXT, weight=ft.FontWeight.W_600, expand=True),
                            ft.IconButton(icon=ft.Icons.REFRESH, on_click=self._refresh_logs),
                            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, on_click=self._clear_logs),
                        ]
                    )
                ),
                log_box,
                ft.ResponsiveRow(
                    controls=[
                        self._card("Platform", self.device.kind.value, ft.Icons.DEVICES_OUTLINED, self.device.machine),
                        self._card("Python", self.device.python_version, ft.Icons.CODE, self.device.python_implementation),
                        self._card(
                            "Features",
                            feature_health_summary(self.feature_results).replace("features=", "").replace(" enabled", ""),
                            ft.Icons.EXTENSION_OUTLINED,
                            "enabled / total",
                        ),
                        self._card("Web UI", str(WEB_PORT) if self.device.is_android else "desktop", ft.Icons.LANGUAGE_OUTLINED),
                    ],
                    spacing=12,
                    run_spacing=12,
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("Runtime endpoint", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.Text(web, color=MUTED, size=11),
                            ft.Text(self.runtime_status.summary(), color=MUTED, size=11),
                            ft.Text(
                                "Action tools · " + (", ".join(self.runtime_status.action_tools) or "none"),
                                color=MUTED,
                                size=11,
                            ),
                        ],
                        spacing=6,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("Session Control", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.Text(
                                "Hapus history jangka pendek tanpa menghapus memory, personality, jadwal, atau konfigurasi.",
                                color=MUTED,
                                size=11,
                            ),
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Button(
                                        "Reset Channel Terpilih",
                                        icon=ft.Icons.RESTART_ALT,
                                        on_click=self._reset_current_session,
                                    ),
                                    ft.Button(
                                        "Reset Semua Session",
                                        icon=ft.Icons.DELETE_SWEEP,
                                        on_click=self._reset_all_sessions,
                                    ),
                                ]
                            ),
                            self.settings_status,
                        ],
                        spacing=10,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("Process Control", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.Text(
                                "Restart atau matikan Senna melalui graceful shutdown.",
                                color=MUTED,
                                size=11,
                            ),
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Button(
                                        "Restart Bot",
                                        icon=ft.Icons.RESTART_ALT,
                                        on_click=self._request_restart,
                                    ),
                                    ft.Button(
                                        "Matikan Bot",
                                        icon=ft.Icons.POWER_SETTINGS_NEW,
                                        on_click=self._request_shutdown,
                                    ),
                                    ft.Button(
                                        "Logout",
                                        icon=ft.Icons.LOGOUT,
                                        on_click=self._logout,
                                        visible=bool(WEB_PIN and self.device.is_android),
                                    ),
                                ]
                            ),
                        ],
                        spacing=10,
                    )
                ),
            ]
        )

    # ---------- navigation ----------
    def _view_for_index(self, index: int) -> ft.Control:
        builders = [
            self._dashboard,
            self._terminal_chat,
            self._emoji,
            self._voice,
            self._ai_settings,
            self._settings,
        ]
        return builders[index]()

    async def _nav_changed(self, e: Any) -> None:
        self._selected_index = int(e.control.selected_index)
        try:
            self.content.content = self._view_for_index(self._selected_index)
        except Exception as error:
            print(
                f"[SENA UI] page build failed index={self._selected_index} "
                f"type={type(error).__name__} detail={error}"
            )
            self.content.content = self._body(
                [
                    self._title("UI Error", "Halaman gagal dibangun, runtime bot tetap hidup"),
                    self._panel(
                        ft.Text(
                            f"{type(error).__name__}: {error}",
                            color=ERROR,
                            selectable=True,
                        )
                    ),
                ]
            )
        if self.page:
            self.page.update()

    def _nav(self) -> ft.NavigationRail:
        return ft.NavigationRail(
            selected_index=self._selected_index,
            extended=not self._compact,
            width=78 if self._compact else 220,
            min_width=72,
            min_extended_width=220,
            bgcolor=SIDEBAR,
            indicator_color="#202020",
            on_change=self._nav_changed,
            leading=ft.Container(
                padding=12,
                content=ft.Text(
                    "S" if self._compact else "SENNA",
                    color=TEXT,
                    weight=ft.FontWeight.BOLD,
                ),
            ),
            destinations=[
                ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, label="Dashboard"),
                ft.NavigationRailDestination(icon=ft.Icons.FORUM_OUTLINED, label="Terminal Chat"),
                ft.NavigationRailDestination(icon=ft.Icons.EMOJI_EMOTIONS_OUTLINED, label="Emoji"),
                ft.NavigationRailDestination(icon=ft.Icons.GRAPHIC_EQ_OUTLINED, label="Voice"),
                ft.NavigationRailDestination(icon=ft.Icons.PSYCHOLOGY_OUTLINED, label="AI Setting"),
                ft.NavigationRailDestination(icon=ft.Icons.SETTINGS_OUTLINED, label="Settings"),
            ],
        )

    def _configure_page(self, page: ft.Page) -> None:
        page.title = "Senna Control Center"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = BG
        page.padding = 0
        page.spacing = 0
        page.theme = ft.Theme(color_scheme_seed="#AFAFAF")

    def _mount_dashboard(self, page: ft.Page) -> None:
        page.clean()
        self.content.content = self._dashboard()
        page.add(
            ft.Row(
                controls=[
                    self._nav(),
                    ft.VerticalDivider(width=1, color=BORDER),
                    self.content,
                ],
                expand=True,
                spacing=0,
            )
        )
        print(
            f"[SENA UI] Browser connected; dashboard ready "
            f"mode={'web' if self.device.is_android else 'desktop'} "
            f"layout={'compact' if self._compact else 'desktop'}"
        )

    def _mount_login(self, page: ft.Page) -> None:
        page.clean()
        pin = ft.TextField(
            label="PIN dashboard",
            password=True,
            can_reveal_password=True,
            autofocus=True,
            width=320,
        )
        status = ft.Text("", color=ERROR, size=11)

        async def submit(e: Any) -> None:
            del e
            if hmac.compare_digest(str(pin.value or ""), WEB_PIN):
                pin.value = ""
                self._mount_dashboard(page)
                page.update()
                return
            pin.value = ""
            status.value = "PIN salah."
            page.update()

        pin.on_submit = submit
        page.add(
            ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                content=self._panel(
                    ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.LOCK_OUTLINE, size=38, color=TEXT),
                            ft.Text("Senna Control Center", size=24, color=TEXT),
                            ft.Text("Masukkan PIN untuk membuka dashboard.", color=MUTED),
                            pin,
                            ft.Button("Masuk", icon=ft.Icons.LOGIN, on_click=submit),
                            status,
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        tight=True,
                        spacing=12,
                    ),
                    padding=28,
                ),
            )
        )

    async def _logout(self, e: Any) -> None:
        del e
        if self.page is not None and WEB_PIN:
            self._mount_login(self.page)
            self.page.update()

    async def main(self, page: ft.Page) -> None:
        self.page = page
        self._compact = bool((page.width or 1200) < 820)
        self._configure_page(page)
        if self.device.is_android and WEB_PIN:
            self._mount_login(page)
        else:
            self._mount_dashboard(page)
        page.run_task(self._log_pump)

    async def run(self) -> None:
        view = ft.AppView.WEB_BROWSER if self.device.is_android else ft.AppView.FLET_APP
        if self.device.is_android:
            if WEB_HOST.casefold() not in _LOOPBACK_HOSTS and not WEB_PIN:
                print(
                    "[SENA SECURITY] Web UI terbuka ke LAN tanpa PIN. "
                    "Isi SENA_WEB_PIN untuk mengaktifkan halaman login."
                )
            print(f"[SENA UI] Starting web server host={WEB_HOST} port={WEB_PORT}")
            print(f"[SENA UI] Open on this phone: http://127.0.0.1:{WEB_PORT}")
            print(f"[SENA UI] Open from laptop: http://<PHONE-LAN-IP>:{WEB_PORT}")
            app_task = asyncio.create_task(
                ft.run_async(self.main, view=view, host=WEB_HOST, port=WEB_PORT),
                name="senna-flet-app",
            )
        else:
            app_task = asyncio.create_task(
                ft.run_async(self.main, view=view),
                name="senna-flet-app",
            )

        shutdown_task = asyncio.create_task(
            self._shutdown_event.wait(),
            name="senna-ui-shutdown-request",
        )
        done, _ = await asyncio.wait(
            {app_task, shutdown_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if app_task in done:
            shutdown_task.cancel()
            await asyncio.gather(shutdown_task, return_exceptions=True)
            await app_task
            return

        app_task.cancel()
        await asyncio.gather(app_task, return_exceptions=True)
