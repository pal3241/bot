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
from core.feature_loader import FeatureLoadResult, feature_health_summary


BG = "#050505"
SIDEBAR = "#0A0A0A"
PANEL = "#101010"
PANEL_2 = "#151515"
BORDER = "#242424"
TEXT = "#F5F5F5"
MUTED = "#8E8E93"
ACCENT = "#FFFFFF"
SUCCESS = "#63D297"
ERROR = "#FF6B6B"
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
    def __init__(self, ctx: AppContext, device: DeviceInfo, feature_results: dict[str, FeatureLoadResult]) -> None:
        self.ctx = ctx
        self.device = device
        self.feature_results = feature_results
        self.page: ft.Page | None = None
        self._selected_index = 0
        self._logs: deque[str] = deque(maxlen=800)
        self._chat_lines: deque[str] = deque(maxlen=300)
        self._log_lock = threading.Lock()
        self._stdout_original = sys.stdout
        self._stderr_original = sys.stderr
        self._capture_installed = False
        self.content = ft.Container(expand=True, bgcolor=BG, padding=26)
        self.log_view = ft.TextField(value="", multiline=True, read_only=True, expand=True, text_size=12, color="#C9C9C9", bgcolor="#080808", border_color=BORDER)
        self.chat_view = ft.TextField(value="", multiline=True, read_only=True, expand=True, text_size=13, color="#D8D8D8", bgcolor="#080808", border_color=BORDER)
        self.chat_input = ft.TextField(hint_text="Ketik pesan ke Discord...", expand=True, bgcolor=PANEL, border_color=BORDER, color=TEXT)
        self.chat_guild = ft.Dropdown(label="Server", expand=True, on_select=self._chat_guild_changed)
        self.chat_channel = ft.Dropdown(label="Channel", expand=True)
        self.voice_guild = ft.Dropdown(label="Server", expand=True, on_select=self._voice_guild_changed)
        self.voice_channel = ft.Dropdown(label="Voice Channel", expand=True)
        self.voice_status = ft.Text("Voice idle", color=MUTED)
        self.emoji_guild = ft.Dropdown(label="Server", expand=True, on_select=self._emoji_guild_changed)
        self.emoji_list = ft.TextField(value="", multiline=True, read_only=True, expand=True, bgcolor="#080808", border_color=BORDER, color="#D8D8D8")
        self.ai_status = ft.Text("", color=MUTED)

    def capture_log(self, text: str) -> None:
        with self._log_lock:
            for line in text.replace("\r", "").splitlines():
                if line.strip(): self._logs.append(line)

    def install_log_capture(self) -> None:
        if self._capture_installed: return
        sys.stdout = _TeeStream(self._stdout_original, self)
        sys.stderr = _TeeStream(self._stderr_original, self)
        self._capture_installed = True
        self.capture_log("[SENA UI] Flet log capture enabled")

    def restore_log_capture(self) -> None:
        if not self._capture_installed: return
        sys.stdout = self._stdout_original
        sys.stderr = self._stderr_original
        self._capture_installed = False

    async def notify_discord_message(self, message: discord.Message) -> None:
        if message.author.bot: return
        channel_name = getattr(message.channel, "name", str(message.channel.id))
        self._chat_lines.append(f"{message.author.display_name}  ·  #{channel_name}\n{message.content}")
        if self.page is not None and self._selected_index == 1:
            self.chat_view.value = "\n\n".join(self._chat_lines)
            self.page.update()

    def _options(self, items: list[tuple[int, str]]) -> list[ft.DropdownOption]:
        return [ft.DropdownOption(key=str(item_id), text=name) for item_id, name in items]

    def _guild_options(self) -> list[ft.DropdownOption]:
        return self._options([(guild.id, guild.name) for guild in self.ctx.client.guilds])

    def _panel(self, content: ft.Control, *, expand: bool = False) -> ft.Container:
        return ft.Container(content=content, padding=20, bgcolor=PANEL, border=ft.Border.all(1, BORDER), border_radius=14, expand=expand)

    def _title(self, title: str, subtitle: str) -> ft.Column:
        return ft.Column(spacing=4, controls=[ft.Text(title, size=26, weight=ft.FontWeight.W_600, color=TEXT), ft.Text(subtitle, size=13, color=MUTED)])

    def _stat_card(self, label: str, value: str, icon: str) -> ft.Container:
        return self._panel(ft.Column(spacing=12, controls=[ft.Icon(icon, color="#BDBDBD", size=22), ft.Text(value, size=22, weight=ft.FontWeight.W_600, color=TEXT), ft.Text(label, size=12, color=MUTED)]), expand=True)

    def _dashboard(self) -> ft.Control:
        client = self.ctx.client
        return ft.Column(expand=True, spacing=20, controls=[
            self._title("Dashboard", "Runtime overview Senna"),
            ft.Row(spacing=14, controls=[self._stat_card("Bot", str(client.user) if client.user else "Offline", ft.Icons.SMART_TOY_OUTLINED), self._stat_card("Servers", str(len(client.guilds)), ft.Icons.DNS_OUTLINED), self._stat_card("AI", "Enabled" if self.ctx.assistant is not None else "Disabled", ft.Icons.PSYCHOLOGY_OUTLINED), self._stat_card("Device", self.device.kind.value, ft.Icons.DEVICES_OUTLINED)]),
            self._panel(ft.Column(spacing=12, controls=[ft.Text("Runtime health", size=16, weight=ft.FontWeight.W_600, color=TEXT), ft.Text(feature_health_summary(self.feature_results), color="#D0D0D0"), ft.Divider(height=1, color=BORDER), ft.Text(f"Python {self.device.python_version} · {self.device.machine}", color=MUTED), ft.Text("Action System aktif bersama Discord AI Router selama subsystem berhasil dimuat.", color=MUTED)])),
        ])

    async def _chat_guild_changed(self, e: Any) -> None:
        guild = self.ctx.client.get_guild(int(self.chat_guild.value)) if self.chat_guild.value else None
        channels = list(guild.text_channels) if guild else []
        self.chat_channel.options = self._options([(c.id, f"#{c.name}") for c in channels]); self.chat_channel.value = str(channels[0].id) if channels else None
        if self.page: self.page.update()

    async def _send_chat(self, e: Any) -> None:
        del e
        value = (self.chat_input.value or "").strip()
        if not value or not self.chat_channel.value: return
        channel = self.ctx.client.get_channel(int(self.chat_channel.value))
        if not isinstance(channel, discord.TextChannel): self._chat_lines.append("SYSTEM\nChannel tidak valid.")
        else:
            try:
                await channel.send(value); self._chat_lines.append(f"You  ·  #{channel.name}\n{value}"); self.chat_input.value = ""
            except Exception as error: self._chat_lines.append(f"SYSTEM\nSend gagal: {type(error).__name__}: {error}")
        self.chat_view.value = "\n\n".join(self._chat_lines)
        if self.page: self.page.update()

    def _terminal_chat(self) -> ft.Control:
        self.chat_guild.options = self._guild_options()
        if self.chat_guild.value is None and self.ctx.client.guilds:
            guild = self.ctx.client.guilds[0]; self.chat_guild.value = str(guild.id); self.chat_channel.options = self._options([(c.id, f"#{c.name}") for c in guild.text_channels])
            if guild.text_channels: self.chat_channel.value = str(guild.text_channels[0].id)
        self.chat_view.value = "\n\n".join(self._chat_lines)
        return ft.Column(expand=True, spacing=16, controls=[self._title("Terminal Chat", "Kirim dan pantau pesan Discord tanpa menu CLI"), ft.Row([self.chat_guild, self.chat_channel], spacing=12), self._panel(self.chat_view, expand=True), ft.Row([self.chat_input, ft.Button("Send", icon=ft.Icons.SEND_ROUNDED, on_click=self._send_chat)], spacing=10)])

    async def _emoji_guild_changed(self, e: Any) -> None:
        del e; self._refresh_emoji_list()
        if self.page: self.page.update()

    def _refresh_emoji_list(self) -> None:
        guild = self.ctx.client.get_guild(int(self.emoji_guild.value)) if self.emoji_guild.value else None
        if guild is None: self.emoji_list.value = "Pilih server."; return
        lines = [f"{emoji.name}  ·  id={emoji.id}  ·  {'animated' if emoji.animated else 'static'}" for emoji in guild.emojis]
        self.emoji_list.value = "\n".join(lines) if lines else "Belum ada custom emoji di server ini."

    def _emoji(self) -> ft.Control:
        self.emoji_guild.options = self._guild_options()
        if self.emoji_guild.value is None and self.ctx.client.guilds: self.emoji_guild.value = str(self.ctx.client.guilds[0].id)
        self._refresh_emoji_list()
        return ft.Column(expand=True, spacing=16, controls=[self._title("Emoji", "Custom emoji inventory dan management workspace"), self.emoji_guild, self._panel(self.emoji_list, expand=True), ft.Text("Import/compress workflow lama tetap tersedia di backend; kontrol upload Flet akan dipindahkan bertahap.", color=MUTED, size=12)])

    async def _voice_guild_changed(self, e: Any) -> None:
        del e
        guild = self.ctx.client.get_guild(int(self.voice_guild.value)) if self.voice_guild.value else None; channels = list(guild.voice_channels) if guild else []
        self.voice_channel.options = self._options([(c.id, c.name) for c in channels]); self.voice_channel.value = str(channels[0].id) if channels else None
        if self.page: self.page.update()

    async def _voice_join(self, e: Any) -> None:
        del e
        if not self.voice_channel.value:
            self.voice_status.value = "Pilih voice channel dulu."; self.voice_status.color = ERROR
            if self.page: self.page.update()
            return
        channel = self.ctx.client.get_channel(int(self.voice_channel.value))
        if not isinstance(channel, discord.VoiceChannel):
            self.voice_status.value = "Voice channel tidak valid."; self.voice_status.color = ERROR
            if self.page: self.page.update()
            return
        try:
            existing = channel.guild.voice_client
            if existing is not None and existing.is_connected():
                if existing.channel is None or existing.channel.id != channel.id: await existing.move_to(channel)
            else: await channel.connect()
            self.voice_status.value = f"Connected · {channel.guild.name} / {channel.name}"; self.voice_status.color = SUCCESS
        except Exception as error:
            self.voice_status.value = f"Join gagal · {type(error).__name__}: {error}"; self.voice_status.color = ERROR; print(f"[SENA UI VOICE] join failed type={type(error).__name__} detail={error}")
        if self.page: self.page.update()

    async def _voice_leave(self, e: Any) -> None:
        del e
        guild = self.ctx.client.get_guild(int(self.voice_guild.value)) if self.voice_guild.value else None
        try:
            if guild is not None and guild.voice_client is not None: await guild.voice_client.disconnect(force=False)
            self.voice_status.value = "Disconnected"; self.voice_status.color = MUTED
        except Exception as error: self.voice_status.value = f"Leave gagal · {type(error).__name__}: {error}"; self.voice_status.color = ERROR
        if self.page: self.page.update()

    def _voice(self) -> ft.Control:
        self.voice_guild.options = self._guild_options()
        if self.voice_guild.value is None and self.ctx.client.guilds:
            guild = self.ctx.client.guilds[0]; self.voice_guild.value = str(guild.id); self.voice_channel.options = self._options([(c.id, c.name) for c in guild.voice_channels])
            if guild.voice_channels: self.voice_channel.value = str(guild.voice_channels[0].id)
        return ft.Column(expand=True, spacing=16, controls=[self._title("Voice", "Voice transport, TTS, STT dan Music foundation"), ft.Row([self.voice_guild, self.voice_channel], spacing=12), self._panel(ft.Column(spacing=14, controls=[self.voice_status, ft.Row([ft.Button("Join", icon=ft.Icons.CALL_ROUNDED, on_click=self._voice_join), ft.Button("Leave", icon=ft.Icons.CALL_END_ROUNDED, on_click=self._voice_leave)], spacing=10), ft.Divider(height=1, color=BORDER), ft.Text("Music controls akan ditempatkan di halaman ini setelah voice transport Termux/DAVE selesai.", color=MUTED)]))])

    async def _apply_ai_settings(self, e: Any) -> None:
        del e; manager = self.ctx.assistant
        if manager is None:
            self.ai_status.value = "AI Assistant tidak aktif."; self.ai_status.color = ERROR
            if self.page: self.page.update()
            return
        try:
            updated = replace(manager.settings, provider_name=str(self.ai_provider.value), openrouter_model=(self.ai_openrouter.value or "").strip(), nvidia_nim_model=(self.ai_nvidia.value or "").strip(), max_tokens=int(self.ai_tokens.value or "0"), request_timeout_seconds=float(self.ai_timeout.value or "0"))
            await manager.apply_settings(updated); save_settings(AI_SETTINGS_FILE, updated); self.ai_status.value = "AI settings applied & saved."; self.ai_status.color = SUCCESS
        except Exception as error: self.ai_status.value = f"Apply gagal · {type(error).__name__}: {error}"; self.ai_status.color = ERROR
        if self.page: self.page.update()

    def _ai_settings(self) -> ft.Control:
        manager = self.ctx.assistant; settings = manager.settings if manager is not None else None
        self.ai_provider = ft.Dropdown(label="Provider", value=settings.provider_name if settings else "nvidia_nim", options=[ft.DropdownOption(key="nvidia_nim", text="NVIDIA NIM"), ft.DropdownOption(key="openrouter", text="OpenRouter")])
        self.ai_openrouter = ft.TextField(label="OpenRouter model", value=settings.openrouter_model if settings else "", border_color=BORDER); self.ai_nvidia = ft.TextField(label="NVIDIA NIM model", value=settings.nvidia_nim_model if settings else "", border_color=BORDER); self.ai_tokens = ft.TextField(label="Max tokens", value=str(settings.max_tokens if settings else 300), border_color=BORDER); self.ai_timeout = ft.TextField(label="Request timeout (s)", value=str(settings.request_timeout_seconds if settings else 60), border_color=BORDER)
        return ft.Column(expand=True, spacing=16, controls=[self._title("AI Setting", "Provider, model dan runtime inference"), self._panel(ft.Column(spacing=14, controls=[self.ai_provider, self.ai_openrouter, self.ai_nvidia, ft.Row([self.ai_tokens, self.ai_timeout], spacing=12), ft.Row([ft.Button("Apply settings", icon=ft.Icons.SAVE_OUTLINED, on_click=self._apply_ai_settings), self.ai_status], spacing=12)]))])

    async def _refresh_logs(self, e: Any = None) -> None:
        del e
        with self._log_lock: self.log_view.value = "\n".join(self._logs)
        if self.page: self.page.update()

    async def _clear_logs(self, e: Any) -> None:
        del e
        with self._log_lock: self._logs.clear()
        await self._refresh_logs()

    async def _log_pump(self) -> None:
        while self.page is not None:
            if self._selected_index == 5: await self._refresh_logs()
            await asyncio.sleep(0.8)

    def _settings(self) -> ft.Control:
        with self._log_lock: self.log_view.value = "\n".join(self._logs)
        return ft.Column(expand=True, spacing=16, controls=[self._title("Settings", "Runtime logs dan pengaturan aplikasi"), self._panel(ft.Row(controls=[ft.Text(f"{self.device.kind.value} · Python {self.device.python_version} · {self.device.machine}", color=MUTED, expand=True), ft.Button("Refresh logs", icon=ft.Icons.REFRESH, on_click=self._refresh_logs), ft.Button("Clear", icon=ft.Icons.DELETE_OUTLINE, on_click=self._clear_logs)])), self._panel(self.log_view, expand=True)])

    def _view_for_index(self, index: int) -> ft.Control:
        return [self._dashboard, self._terminal_chat, self._emoji, self._voice, self._ai_settings, self._settings][index]()

    async def _nav_changed(self, e: Any) -> None:
        self._selected_index = int(e.control.selected_index); self.content.content = self._view_for_index(self._selected_index)
        if self.page: self.page.update()

    async def main(self, page: ft.Page) -> None:
        self.page = page; page.title = "Senna Control Center"; page.theme_mode = ft.ThemeMode.DARK; page.bgcolor = BG; page.padding = 0; page.spacing = 0; page.theme = ft.Theme(color_scheme_seed="#AFAFAF")
        rail = ft.NavigationRail(selected_index=0, extended=True, width=215, min_extended_width=215, bgcolor=SIDEBAR, indicator_color="#202020", on_change=self._nav_changed, leading=ft.Container(padding=ft.Padding.only(left=12, right=12, top=18, bottom=22), content=ft.Row([ft.Container(width=34, height=34, border_radius=10, bgcolor="#F2F2F2", alignment=ft.Alignment.CENTER, content=ft.Text("S", color="#000000", weight=ft.FontWeight.BOLD)), ft.Column([ft.Text("SENNA", color=TEXT, weight=ft.FontWeight.W_600), ft.Text("CONTROL CENTER", color=MUTED, size=9)], spacing=0)], spacing=10)), destinations=[ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Dashboard"), ft.NavigationRailDestination(icon=ft.Icons.FORUM_OUTLINED, selected_icon=ft.Icons.FORUM, label="Terminal Chat"), ft.NavigationRailDestination(icon=ft.Icons.EMOJI_EMOTIONS_OUTLINED, selected_icon=ft.Icons.EMOJI_EMOTIONS, label="Emoji"), ft.NavigationRailDestination(icon=ft.Icons.GRAPHIC_EQ_OUTLINED, selected_icon=ft.Icons.GRAPHIC_EQ, label="Voice"), ft.NavigationRailDestination(icon=ft.Icons.PSYCHOLOGY_OUTLINED, selected_icon=ft.Icons.PSYCHOLOGY, label="AI Setting"), ft.NavigationRailDestination(icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS, label="Settings")])
        self.content.content = self._dashboard(); page.add(ft.Row(expand=True, spacing=0, controls=[rail, ft.VerticalDivider(width=1, color=BORDER), self.content])); page.run_task(self._log_pump); print(f"[SENA UI] Browser connected; dashboard ready mode={'web' if self.device.is_android else 'desktop'}")

    async def run(self) -> None:
        self.install_log_capture(); view = ft.AppView.WEB_BROWSER if self.device.is_android else ft.AppView.FLET_APP
        try:
            if self.device.is_android:
                print(f"[SENA UI] Starting web server host={WEB_HOST} port={WEB_PORT}")
                print(f"[SENA UI] Open on this phone: http://127.0.0.1:{WEB_PORT}")
                print(f"[SENA UI] Open from laptop: http://<PHONE-LAN-IP>:{WEB_PORT}")
                await ft.run_async(self.main, view=view, host=WEB_HOST, port=WEB_PORT)
            else:
                await ft.run_async(self.main, view=view)
        finally:
            self.page = None; self.restore_log_capture()
