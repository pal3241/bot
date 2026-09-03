from __future__ import annotations

import asyncio
import io
import os
import sys
import threading
from collections import deque
from dataclasses import replace
from typing import Any

import discord
import flet as ft

from assistant.settings import save_settings
from config import AI_SETTINGS_FILE
from core.context import AppContext
from core.device import DeviceInfo
from core.feature_loader import FeatureLoadResult, FeatureLoadState, feature_health_summary
from core.runtime_status import RuntimeStatus


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
WEB_HOST = os.getenv("SENA_WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("SENA_WEB_PORT", "8550"))


class _TeeStream(io.TextIOBase):
    def __init__(self, original: Any, sink: "SenaFletUI") -> None:
        self._original = original
        self._sink = sink

    def write(self, text: str) -> int:
        written = self._original.write(text)
        self._original.flush()
        if text:
            self._sink.capture_log(text)
        return written

    def flush(self) -> None:
        self._original.flush()


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
        self._logs: deque[str] = deque(maxlen=1000)
        self._chat_lines: deque[str] = deque(maxlen=400)
        self._log_lock = threading.Lock()
        self._stdout_original = sys.stdout
        self._stderr_original = sys.stderr
        self._capture_installed = False

        self.content = ft.Container(expand=True, bgcolor=BG)
        self.log_view = ft.TextField(
            value="",
            multiline=True,
            read_only=True,
            expand=True,
            text_size=12,
            color="#C9C9C9",
            bgcolor="#080808",
            border_color=BORDER,
        )
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
            label="Server",
            expand=True,
            on_select=self._chat_guild_changed,
        )
        self.chat_channel = ft.Dropdown(label="Channel", expand=True)
        self.voice_guild = ft.Dropdown(
            label="Server",
            expand=True,
            on_select=self._voice_guild_changed,
        )
        self.voice_channel = ft.Dropdown(label="Voice Channel", expand=True)
        self.voice_status = ft.Text("Voice idle", color=MUTED)
        self.emoji_guild = ft.Dropdown(
            label="Server",
            expand=True,
            on_select=self._emoji_guild_changed,
        )
        self.emoji_list = ft.TextField(
            value="",
            multiline=True,
            read_only=True,
            expand=True,
            bgcolor="#080808",
            border_color=BORDER,
            color="#D8D8D8",
        )
        self.ai_status = ft.Text("", color=MUTED)

    def capture_log(self, text: str) -> None:
        with self._log_lock:
            for line in text.replace("\r", "").splitlines():
                if line.strip():
                    self._logs.append(line)

    def install_log_capture(self) -> None:
        if self._capture_installed:
            return
        sys.stdout = _TeeStream(self._stdout_original, self)
        sys.stderr = _TeeStream(self._stderr_original, self)
        self._capture_installed = True
        self.capture_log("[SENA UI] Flet log capture enabled")

    def restore_log_capture(self) -> None:
        if not self._capture_installed:
            return
        sys.stdout = self._stdout_original
        sys.stderr = self._stderr_original
        self._capture_installed = False

    async def notify_discord_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        channel_name = getattr(message.channel, "name", str(message.channel.id))
        self._chat_lines.append(
            f"{message.author.display_name}  ·  #{channel_name}\n{message.content}"
        )
        if self.page is not None and self._selected_index == 1:
            self.chat_view.value = "\n\n".join(self._chat_lines)
            self.page.update()

    def _options(self, items: list[tuple[int, str]]) -> list[ft.DropdownOption]:
        return [
            ft.DropdownOption(key=str(item_id), text=name)
            for item_id, name in items
        ]

    def _guild_options(self) -> list[ft.DropdownOption]:
        return self._options(
            [(guild.id, guild.name) for guild in self.ctx.client.guilds]
        )

    def _panel(
        self,
        content: ft.Control,
        *,
        expand: bool = False,
        padding: int = 18,
    ) -> ft.Container:
        return ft.Container(
            content=content,
            padding=padding,
            bgcolor=PANEL,
            border=ft.Border.all(1, BORDER),
            border_radius=16,
            expand=expand,
        )

    def _page_body(self, controls: list[ft.Control]) -> ft.Container:
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
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    spacing=2,
                    expand=True,
                    controls=[
                        ft.Text(
                            title,
                            size=23 if self._compact else 28,
                            weight=ft.FontWeight.W_600,
                            color=TEXT,
                            no_wrap=False,
                        ),
                        ft.Text(subtitle, size=12 if self._compact else 13, color=MUTED),
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    border=ft.Border.all(1, BORDER),
                    border_radius=20,
                    bgcolor=PANEL,
                    content=ft.Text(
                        "ONLINE" if self.ctx.client.is_ready() else "STARTING",
                        color=SUCCESS if self.ctx.client.is_ready() else WARNING,
                        size=10,
                        weight=ft.FontWeight.W_600,
                    ),
                ),
            ],
        )

    def _status_color(self, enabled: bool) -> str:
        return SUCCESS if enabled else ERROR

    def _status_badge(self, label: str, enabled: bool) -> ft.Container:
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border=ft.Border.all(1, BORDER),
            border_radius=18,
            bgcolor=PANEL_2,
            content=ft.Row(
                spacing=7,
                tight=True,
                controls=[
                    ft.Container(
                        width=7,
                        height=7,
                        border_radius=99,
                        bgcolor=self._status_color(enabled),
                    ),
                    ft.Text(label, color="#D6D6D6", size=11),
                ],
            ),
        )

    def _stat_card(
        self,
        label: str,
        value: str,
        icon: str,
        *,
        detail: str = "",
    ) -> ft.Container:
        return ft.Container(
            col={"xs": 12, "sm": 6, "md": 3},
            content=self._panel(
                ft.Column(
                    spacing=9,
                    controls=[
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Icon(icon, color="#BDBDBD", size=20),
                                ft.Container(
                                    width=7,
                                    height=7,
                                    border_radius=99,
                                    bgcolor=SUCCESS,
                                ),
                            ],
                        ),
                        ft.Text(
                            value,
                            size=18 if self._compact else 22,
                            weight=ft.FontWeight.W_600,
                            color=TEXT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(label, size=11, color=MUTED),
                        ft.Text(detail, size=10, color="#66666A") if detail else ft.Container(),
                    ],
                )
            ),
        )

    def _feature_rows(self) -> list[ft.Control]:
        rows: list[ft.Control] = []
        for result in self.feature_results.values():
            enabled = result.state is FeatureLoadState.ENABLED
            state_color = SUCCESS if enabled else WARNING if result.state is FeatureLoadState.SKIPPED else ERROR
            rows.append(
                ft.Container(
                    padding=ft.Padding.symmetric(vertical=8),
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Container(
                                width=8,
                                height=8,
                                margin=ft.Margin.only(top=5),
                                border_radius=99,
                                bgcolor=state_color,
                            ),
                            ft.Column(
                                spacing=1,
                                expand=True,
                                controls=[
                                    ft.Text(result.spec.label, color=TEXT, size=12),
                                    ft.Text(
                                        f"{result.state.value.upper()} · {result.detail}",
                                        color=MUTED,
                                        size=10,
                                    ),
                                ],
                            ),
                        ],
                    ),
                )
            )
        return rows

    def _dashboard(self) -> ft.Control:
        client = self.ctx.client
        runtime = self.runtime_status
        cards = ft.ResponsiveRow(
            spacing=12,
            run_spacing=12,
            controls=[
                self._stat_card(
                    "Discord bot",
                    str(client.user) if client.user else "Offline",
                    ft.Icons.SMART_TOY_OUTLINED,
                    detail="Gateway connected" if client.is_ready() else "Starting",
                ),
                self._stat_card(
                    "Servers",
                    str(len(client.guilds)),
                    ft.Icons.DNS_OUTLINED,
                    detail="Guilds connected",
                ),
                self._stat_card(
                    "AI",
                    "Enabled" if runtime.ai_enabled else "Disabled",
                    ft.Icons.PSYCHOLOGY_OUTLINED,
                    detail="LLM assistant",
                ),
                self._stat_card(
                    "Device",
                    self.device.kind.value,
                    ft.Icons.DEVICES_OUTLINED,
                    detail=self.device.machine,
                ),
            ],
        )
        runtime_badges = ft.Row(
            wrap=True,
            spacing=8,
            run_spacing=8,
            controls=[
                self._status_badge("AI", runtime.ai_enabled),
                self._status_badge("Router", runtime.router_enabled),
                self._status_badge("Actions", runtime.action_enabled),
                self._status_badge("Expression", runtime.expression_enabled),
            ],
        )
        tool_text = ", ".join(runtime.action_tools) if runtime.action_tools else "No action tools loaded"
        return self._page_body(
            [
                self._title("Dashboard", "Runtime overview dan health Senna"),
                cards,
                self._panel(
                    ft.Column(
                        spacing=12,
                        controls=[
                            ft.Text("Core runtime", color=TEXT, size=15, weight=ft.FontWeight.W_600),
                            runtime_badges,
                            ft.Divider(height=1, color=BORDER),
                            ft.Text(runtime.summary(), color="#C9C9C9", size=11),
                            ft.Text(f"Action tools · {tool_text}", color=MUTED, size=11),
                        ],
                    )
                ),
                self._panel(
                    ft.Column(
                        spacing=2,
                        controls=[
                            ft.Text("Feature health", color=TEXT, size=15, weight=ft.FontWeight.W_600),
                            ft.Text(feature_health_summary(self.feature_results), color=MUTED, size=11),
                            ft.Divider(height=10, color=BORDER),
                            *self._feature_rows(),
                        ],
                    )
                ),
            ]
        )

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
        value = (self.chat_input.value or "").strip()
        if not value:
            return
        if not self.chat_channel.value:
            self._chat_lines.append("SYSTEM\nPilih channel sebelum mengirim pesan.")
        else:
            channel = self.ctx.client.get_channel(int(self.chat_channel.value))
            if not isinstance(channel, discord.TextChannel):
                self._chat_lines.append("SYSTEM\nChannel tidak valid.")
            else:
                try:
                    await channel.send(value)
                    self._chat_lines.append(f"Senna  ·  #{channel.name}\n{value}")
                    self.chat_input.value = ""
                except Exception as error:
                    self._chat_lines.append(
                        f"SYSTEM\nSend gagal: {type(error).__name__}: {error}"
                    )
        self.chat_view.value = "\n\n".join(self._chat_lines)
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
            if guild.text_channels:
                self.chat_channel.value = str(guild.text_channels[0].id)
        self.chat_view.value = "\n\n".join(self._chat_lines)
        selector = ft.ResponsiveRow(
            spacing=10,
            run_spacing=10,
            controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=self.chat_guild),
                ft.Container(col={"xs": 12, "md": 6}, content=self.chat_channel),
            ],
        )
        return self._page_body(
            [
                self._title("Terminal Chat", "Kirim dan pantau Discord dari control center"),
                selector,
                ft.Container(
                    height=360 if self._compact else 460,
                    content=self._panel(self.chat_view, expand=True, padding=10),
                ),
                ft.Row(
                    controls=[
                        self.chat_input,
                        ft.IconButton(
                            icon=ft.Icons.SEND_ROUNDED,
                            tooltip="Send",
                            on_click=self._send_chat,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                            tooltip="Clear view",
                            on_click=self._clear_chat,
                        ),
                    ]
                ),
            ]
        )

    async def _emoji_guild_changed(self, e: Any) -> None:
        del e
        self._refresh_emoji_list()
        if self.page:
            self.page.update()

    async def _refresh_emoji(self, e: Any) -> None:
        del e
        self._refresh_emoji_list()
        if self.page:
            self.page.update()

    def _refresh_emoji_list(self) -> None:
        guild = (
            self.ctx.client.get_guild(int(self.emoji_guild.value))
            if self.emoji_guild.value
            else None
        )
        if guild is None:
            self.emoji_list.value = "Pilih server."
            return
        lines = [
            f"{emoji.name}  ·  id={emoji.id}  ·  "
            f"{'animated' if emoji.animated else 'static'}"
            for emoji in guild.emojis
        ]
        self.emoji_list.value = (
            "\n".join(lines) if lines else "Belum ada custom emoji di server ini."
        )

    def _emoji(self) -> ft.Control:
        self.emoji_guild.options = self._guild_options()
        if self.emoji_guild.value is None and self.ctx.client.guilds:
            self.emoji_guild.value = str(self.ctx.client.guilds[0].id)
        self._refresh_emoji_list()
        guild = (
            self.ctx.client.get_guild(int(self.emoji_guild.value))
            if self.emoji_guild.value
            else None
        )
        count = len(guild.emojis) if guild else 0
        return self._page_body(
            [
                self._title("Emoji", "Inventory custom emoji Discord"),
                ft.Row(
                    controls=[
                        self.emoji_guild,
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            tooltip="Refresh",
                            on_click=self._refresh_emoji,
                        ),
                    ]
                ),
                self._panel(
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.EMOJI_EMOTIONS_OUTLINED, color="#BDBDBD"),
                            ft.Column(
                                spacing=0,
                                controls=[
                                    ft.Text(f"{count} custom emoji", color=TEXT, size=16),
                                    ft.Text("Runtime Discord cache", color=MUTED, size=10),
                                ],
                            ),
                        ]
                    )
                ),
                ft.Container(
                    height=380 if self._compact else 500,
                    content=self._panel(self.emoji_list, expand=True, padding=10),
                ),
                ft.Text(
                    "Import/compress backend tetap tersedia; uploader Flet akan disambungkan setelah file-picker workflow dibuat stabil lintas Termux dan desktop.",
                    color=MUTED,
                    size=11,
                ),
            ]
        )

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
            self.voice_status.value = "Pilih voice channel dulu."
            self.voice_status.color = ERROR
            if self.page:
                self.page.update()
            return
        channel = self.ctx.client.get_channel(int(self.voice_channel.value))
        if not isinstance(channel, discord.VoiceChannel):
            self.voice_status.value = "Voice channel tidak valid."
            self.voice_status.color = ERROR
            if self.page:
                self.page.update()
            return
        try:
            existing = channel.guild.voice_client
            if existing is not None and existing.is_connected():
                if existing.channel is None or existing.channel.id != channel.id:
                    await existing.move_to(channel)
            else:
                await channel.connect()
            self.voice_status.value = (
                f"Connected · {channel.guild.name} / {channel.name}"
            )
            self.voice_status.color = SUCCESS
        except Exception as error:
            self.voice_status.value = (
                f"Join gagal · {type(error).__name__}: {error}"
            )
            self.voice_status.color = ERROR
            print(
                f"[SENA UI VOICE] join failed "
                f"type={type(error).__name__} detail={error}"
            )
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
            if guild is not None and guild.voice_client is not None:
                await guild.voice_client.disconnect(force=False)
            self.voice_status.value = "Disconnected"
            self.voice_status.color = MUTED
        except Exception as error:
            self.voice_status.value = (
                f"Leave gagal · {type(error).__name__}: {error}"
            )
            self.voice_status.color = ERROR
        if self.page:
            self.page.update()

    def _voice(self) -> ft.Control:
        self.voice_guild.options = self._guild_options()
        if self.voice_guild.value is None and self.ctx.client.guilds:
            guild = self.ctx.client.guilds[0]
            self.voice_guild.value = str(guild.id)
            self.voice_channel.options = self._options(
                [(c.id, c.name) for c in guild.voice_channels]
            )
            if guild.voice_channels:
                self.voice_channel.value = str(guild.voice_channels[0].id)

        voice_feature = self.feature_results.get("voice")
        voice_backend_ok = bool(voice_feature and voice_feature.available)
        backend_detail = (
            voice_feature.detail if voice_feature else "Voice feature not registered"
        )
        selector = ft.ResponsiveRow(
            spacing=10,
            run_spacing=10,
            controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=self.voice_guild),
                ft.Container(col={"xs": 12, "md": 6}, content=self.voice_channel),
            ],
        )
        return self._page_body(
            [
                self._title("Voice", "Voice transport, TTS, STT dan music foundation"),
                self._panel(
                    ft.Row(
                        controls=[
                            ft.Container(
                                width=9,
                                height=9,
                                border_radius=99,
                                bgcolor=SUCCESS if voice_backend_ok else ERROR,
                            ),
                            ft.Column(
                                spacing=1,
                                expand=True,
                                controls=[
                                    ft.Text(
                                        "Voice backend ready" if voice_backend_ok else "Voice backend degraded",
                                        color=TEXT,
                                        size=13,
                                    ),
                                    ft.Text(backend_detail, color=MUTED, size=10),
                                ],
                            ),
                        ]
                    )
                ),
                selector,
                self._panel(
                    ft.Column(
                        spacing=14,
                        controls=[
                            self.voice_status,
                            ft.Row(
                                wrap=True,
                                controls=[
                                    ft.Button(
                                        "Join",
                                        icon=ft.Icons.CALL_ROUNDED,
                                        on_click=self._voice_join,
                                    ),
                                    ft.Button(
                                        "Leave",
                                        icon=ft.Icons.CALL_END_ROUNDED,
                                        on_click=self._voice_leave,
                                    ),
                                ],
                            ),
                            ft.Divider(height=1, color=BORDER),
                            ft.Text("Music", color=TEXT, size=15, weight=ft.FontWeight.W_600),
                            ft.Text(
                                "Music Action API akan menggunakan voice transport yang sama. UI sudah disiapkan sebagai lokasi player/queue saat backend music.play ditambahkan.",
                                color=MUTED,
                                size=11,
                            ),
                        ],
                    )
                ),
            ]
        )

    async def _apply_ai_settings(self, e: Any) -> None:
        del e
        manager = self.ctx.assistant
        if manager is None:
            self.ai_status.value = "AI Assistant tidak aktif."
            self.ai_status.color = ERROR
            if self.page:
                self.page.update()
            return
        try:
            updated = replace(
                manager.settings,
                provider_name=str(self.ai_provider.value),
                openrouter_model=(self.ai_openrouter.value or "").strip(),
                nvidia_nim_model=(self.ai_nvidia.value or "").strip(),
                max_tokens=int(self.ai_tokens.value or "0"),
                request_timeout_seconds=float(self.ai_timeout.value or "0"),
                retry_count=int(self.ai_retry_count.value or "0"),
                retry_delay_seconds=float(self.ai_retry_delay.value or "0"),
                chat_timeout_seconds=float(self.ai_chat_timeout.value or "0"),
                history_max_messages=int(self.ai_history.value or "0"),
            )
            await manager.apply_settings(updated)
            save_settings(AI_SETTINGS_FILE, updated)
            self.ai_status.value = "AI settings applied & saved."
            self.ai_status.color = SUCCESS
        except Exception as error:
            self.ai_status.value = f"Apply gagal · {type(error).__name__}: {error}"
            self.ai_status.color = ERROR
        if self.page:
            self.page.update()

    def _ai_settings(self) -> ft.Control:
        manager = self.ctx.assistant
        settings = manager.settings if manager is not None else None
        self.ai_provider = ft.Dropdown(
            label="Provider",
            value=settings.provider_name if settings else "nvidia_nim",
            options=[
                ft.DropdownOption(key="nvidia_nim", text="NVIDIA NIM"),
                ft.DropdownOption(key="openrouter", text="OpenRouter"),
            ],
        )
        self.ai_openrouter = ft.TextField(
            label="OpenRouter model",
            value=settings.openrouter_model if settings else "",
            border_color=BORDER,
        )
        self.ai_nvidia = ft.TextField(
            label="NVIDIA NIM model",
            value=settings.nvidia_nim_model if settings else "",
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
            value=str(settings.chat_timeout_seconds if settings else 300),
            border_color=BORDER,
        )
        self.ai_history = ft.TextField(
            label="History messages",
            value=str(settings.history_max_messages if settings else 20),
            border_color=BORDER,
        )
        fields = ft.ResponsiveRow(
            spacing=10,
            run_spacing=10,
            controls=[
                ft.Container(col={"xs": 12, "md": 6}, content=self.ai_provider),
                ft.Container(col={"xs": 12, "md": 6}, content=self.ai_tokens),
                ft.Container(col=12, content=self.ai_nvidia),
                ft.Container(col=12, content=self.ai_openrouter),
                ft.Container(col={"xs": 12, "md": 6}, content=self.ai_timeout),
                ft.Container(col={"xs": 12, "md": 6}, content=self.ai_chat_timeout),
                ft.Container(col={"xs": 12, "md": 6}, content=self.ai_retry_count),
                ft.Container(col={"xs": 12, "md": 6}, content=self.ai_retry_delay),
                ft.Container(col={"xs": 12, "md": 6}, content=self.ai_history),
            ],
        )
        return self._page_body(
            [
                self._title("AI Setting", "Provider, model dan inference runtime"),
                self._panel(
                    ft.Column(
                        spacing=14,
                        controls=[
                            fields,
                            ft.Row(
                                wrap=True,
                                controls=[
                                    ft.Button(
                                        "Apply settings",
                                        icon=ft.Icons.SAVE_OUTLINED,
                                        on_click=self._apply_ai_settings,
                                    ),
                                    self.ai_status,
                                ],
                            ),
                        ],
                    )
                ),
            ]
        )

    async def _refresh_logs(self, e: Any = None) -> None:
        del e
        with self._log_lock:
            self.log_view.value = "\n".join(self._logs)
        if self.page:
            self.page.update()

    async def _clear_logs(self, e: Any) -> None:
        del e
        with self._log_lock:
            self._logs.clear()
        await self._refresh_logs()

    async def _log_pump(self) -> None:
        while self.page is not None:
            if self._selected_index == 5:
                await self._refresh_logs()
            await asyncio.sleep(0.8)

    def _settings(self) -> ft.Control:
        with self._log_lock:
            self.log_view.value = "\n".join(self._logs)
        web_info = (
            f"0.0.0.0:{WEB_PORT} · local http://127.0.0.1:{WEB_PORT}"
            if self.device.is_android
            else "Desktop Flet app"
        )
        return self._page_body(
            [
                self._title("Settings", "Runtime, network dan logs"),
                ft.ResponsiveRow(
                    spacing=12,
                    run_spacing=12,
                    controls=[
                        self._stat_card(
                            "Platform",
                            self.device.kind.value,
                            ft.Icons.DEVICES_OUTLINED,
                            detail=self.device.machine,
                        ),
                        self._stat_card(
                            "Python",
                            self.device.python_version,
                            ft.Icons.CODE,
                            detail=self.device.python_implementation,
                        ),
                        self._stat_card(
                            "Features",
                            feature_health_summary(self.feature_results).replace("features=", "").replace(" enabled", ""),
                            ft.Icons.EXTENSION_OUTLINED,
                            detail="enabled / total",
                        ),
                        self._stat_card(
                            "Web UI",
                            str(WEB_PORT) if self.device.is_android else "desktop",
                            ft.Icons.LANGUAGE_OUTLINED,
                            detail="LAN enabled" if self.device.is_android else "native window",
                        ),
                    ],
                ),
                self._panel(
                    ft.Column(
                        spacing=7,
                        controls=[
                            ft.Text("Runtime endpoint", color=TEXT, size=14, weight=ft.FontWeight.W_600),
                            ft.Text(web_info, color=MUTED, size=11),
                            ft.Text(self.runtime_status.summary(), color=MUTED, size=11),
                        ],
                    )
                ),
                self._panel(
                    ft.Row(
                        wrap=True,
                        controls=[
                            ft.Text("Live logs", color=TEXT, expand=True),
                            ft.Button(
                                "Refresh",
                                icon=ft.Icons.REFRESH,
                                on_click=self._refresh_logs,
                            ),
                            ft.Button(
                                "Clear",
                                icon=ft.Icons.DELETE_OUTLINE,
                                on_click=self._clear_logs,
                            ),
                        ]
                    )
                ),
                ft.Container(
                    height=420 if self._compact else 560,
                    content=self._panel(self.log_view, expand=True, padding=10),
                ),
            ]
        )

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
        self.content.content = self._view_for_index(self._selected_index)
        if self.page:
            self.page.update()

    def _build_navigation(self) -> ft.NavigationRail:
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
                padding=ft.Padding.only(
                    left=10,
                    right=10,
                    top=18,
                    bottom=20,
                ),
                content=(
                    ft.Container(
                        width=38,
                        height=38,
                        border_radius=11,
                        bgcolor="#F1F1F1",
                        alignment=ft.Alignment.CENTER,
                        content=ft.Text(
                            "S",
                            color="#000000",
                            weight=ft.FontWeight.BOLD,
                        ),
                    )
                    if self._compact
                    else ft.Row(
                        spacing=10,
                        controls=[
                            ft.Container(
                                width=38,
                                height=38,
                                border_radius=11,
                                bgcolor="#F1F1F1",
                                alignment=ft.Alignment.CENTER,
                                content=ft.Text(
                                    "S",
                                    color="#000000",
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ),
                            ft.Column(
                                spacing=0,
                                controls=[
                                    ft.Text("SENNA", color=TEXT, weight=ft.FontWeight.W_600),
                                    ft.Text("CONTROL CENTER", color=MUTED, size=9),
                                ],
                            ),
                        ],
                    )
                ),
            ),
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.DASHBOARD_OUTLINED,
                    selected_icon=ft.Icons.DASHBOARD,
                    label="Dashboard",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.FORUM_OUTLINED,
                    selected_icon=ft.Icons.FORUM,
                    label="Terminal Chat",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.EMOJI_EMOTIONS_OUTLINED,
                    selected_icon=ft.Icons.EMOJI_EMOTIONS,
                    label="Emoji",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.GRAPHIC_EQ_OUTLINED,
                    selected_icon=ft.Icons.GRAPHIC_EQ,
                    label="Voice",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.PSYCHOLOGY_OUTLINED,
                    selected_icon=ft.Icons.PSYCHOLOGY,
                    label="AI Setting",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS,
                    label="Settings",
                ),
            ],
        )

    async def main(self, page: ft.Page) -> None:
        self.page = page
        self._compact = bool((page.width or 1200) < 820)
        page.title = "Senna Control Center"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = BG
        page.padding = 0
        page.spacing = 0
        page.theme = ft.Theme(color_scheme_seed="#AFAFAF")

        self.content.content = self._dashboard()
        page.add(
            ft.Row(
                expand=True,
                spacing=0,
                controls=[
                    self._build_navigation(),
                    ft.VerticalDivider(width=1, color=BORDER),
                    self.content,
                ],
            )
        )
        page.run_task(self._log_pump)
        print(
            f"[SENA UI] Browser connected; dashboard ready "
            f"mode={'web' if self.device.is_android else 'desktop'} "
            f"layout={'compact' if self._compact else 'desktop'}"
        )

    async def run(self) -> None:
        self.install_log_capture()
        view = (
            ft.AppView.WEB_BROWSER
            if self.device.is_android
            else ft.AppView.FLET_APP
        )
        try:
            if self.device.is_android:
                print(
                    f"[SENA UI] Starting web server "
                    f"host={WEB_HOST} port={WEB_PORT}"
                )
                print(
                    f"[SENA UI] Open on this phone: "
                    f"http://127.0.0.1:{WEB_PORT}"
                )
                print(
                    f"[SENA UI] Open from laptop: "
                    f"http://<PHONE-LAN-IP>:{WEB_PORT}"
                )
                await ft.run_async(
                    self.main,
                    view=view,
                    host=WEB_HOST,
                    port=WEB_PORT,
                )
            else:
                await ft.run_async(self.main, view=view)
        finally:
            self.page = None
            self.restore_log_capture()
