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
        self.original, self.sink = original, sink
    def write(self, text: str) -> int:
        n = self.original.write(text); self.original.flush()
        if text: self.sink.capture_log(text)
        return n
    def flush(self) -> None: self.original.flush()


class SenaFletUI:
    def __init__(self, ctx: AppContext, device: DeviceInfo, feature_results: dict[str, FeatureLoadResult], runtime_status: RuntimeStatus) -> None:
        self.ctx, self.device = ctx, device
        self.feature_results, self.runtime_status = feature_results, runtime_status
        self.page: ft.Page | None = None
        self._selected_index, self._compact = 0, False
        self._logs: deque[str] = deque(maxlen=1000)
        self._chat_lines: deque[str] = deque(maxlen=400)
        self._log_lock = threading.Lock()
        self._stdout_original, self._stderr_original = sys.stdout, sys.stderr
        self._capture_installed = False
        self.content = ft.Container(expand=True, bgcolor=BG)
        # Logs are deliberately plain Text inside a dark scroll container. A read-only
        # TextField can render its native HTML input surface light/grey in Flet Web.
        self.log_text = ft.Text("", size=12, color="#C9C9C9", selectable=True)
        self.log_scroll = ft.Column([self.log_text], scroll=ft.ScrollMode.AUTO, expand=True)
        self.chat_view = ft.TextField(value="", multiline=True, read_only=True, expand=True, text_size=13, color="#D8D8D8", bgcolor="#080808", border_color=BORDER)
        self.chat_input = ft.TextField(hint_text="Ketik pesan ke Discord...", expand=True, bgcolor=PANEL, border_color=BORDER, color=TEXT, on_submit=self._send_chat)
        self.chat_guild = ft.Dropdown(label="Server", expand=True, on_select=self._chat_guild_changed)
        self.chat_channel = ft.Dropdown(label="Channel", expand=True)
        self.voice_guild = ft.Dropdown(label="Server", expand=True, on_select=self._voice_guild_changed)
        self.voice_channel = ft.Dropdown(label="Voice Channel", expand=True)
        self.voice_status = ft.Text("Voice idle", color=MUTED)
        self.emoji_guild = ft.Dropdown(label="Server", expand=True, on_select=self._emoji_guild_changed)
        self.emoji_text = ft.Text("", size=12, color="#D8D8D8", selectable=True)
        self.ai_status = ft.Text("", color=MUTED)

    def capture_log(self, text: str) -> None:
        with self._log_lock:
            for line in text.replace("\r", "").splitlines():
                if line.strip(): self._logs.append(line)
    def install_log_capture(self) -> None:
        if self._capture_installed: return
        sys.stdout, sys.stderr = _TeeStream(self._stdout_original, self), _TeeStream(self._stderr_original, self)
        self._capture_installed = True; self.capture_log("[SENA UI] Flet log capture enabled")
    def restore_log_capture(self) -> None:
        if self._capture_installed:
            sys.stdout, sys.stderr = self._stdout_original, self._stderr_original; self._capture_installed = False

    async def notify_discord_message(self, message: discord.Message) -> None:
        if message.author.bot: return
        name = getattr(message.channel, "name", str(message.channel.id))
        self._chat_lines.append(f"{message.author.display_name} · #{name}\n{message.content}")
        if self.page and self._selected_index == 1:
            self.chat_view.value = "\n\n".join(self._chat_lines); self.page.update()

    def _panel(self, content: ft.Control, *, expand: bool = False, padding: int = 18) -> ft.Container:
        return ft.Container(content=content, padding=padding, bgcolor=PANEL, border=ft.Border.all(1, BORDER), border_radius=16, expand=expand)
    def _body(self, controls: list[ft.Control]) -> ft.Container:
        return ft.Container(expand=True, padding=18 if self._compact else 28, content=ft.Column(controls, spacing=16, expand=True, scroll=ft.ScrollMode.AUTO))
    def _title(self, title: str, subtitle: str) -> ft.Row:
        return ft.Row([ft.Column([ft.Text(title, size=23 if self._compact else 28, weight=ft.FontWeight.W_600, color=TEXT), ft.Text(subtitle, size=12, color=MUTED)], spacing=2, expand=True), ft.Text("ONLINE" if self.ctx.client.is_ready() else "STARTING", color=SUCCESS if self.ctx.client.is_ready() else WARNING, size=10)])
    def _options(self, items: list[tuple[int, str]]) -> list[ft.DropdownOption]:
        return [ft.DropdownOption(key=str(i), text=n) for i, n in items]
    def _guild_options(self) -> list[ft.DropdownOption]: return self._options([(g.id, g.name) for g in self.ctx.client.guilds])
    def _card(self, label: str, value: str, icon: str, detail: str = "") -> ft.Container:
        return ft.Container(col={"xs":12,"sm":6,"md":3}, content=self._panel(ft.Column([ft.Icon(icon, color="#BDBDBD"), ft.Text(value, size=19, weight=ft.FontWeight.W_600, color=TEXT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS), ft.Text(label, size=11, color=MUTED), ft.Text(detail, size=10, color="#66666A")], spacing=8)))

    def _dashboard(self) -> ft.Control:
        r = self.runtime_status
        cards = ft.ResponsiveRow([self._card("Discord bot", str(self.ctx.client.user or "Offline"), ft.Icons.SMART_TOY_OUTLINED), self._card("Servers", str(len(self.ctx.client.guilds)), ft.Icons.DNS_OUTLINED), self._card("AI", "Enabled" if r.ai_enabled else "Disabled", ft.Icons.PSYCHOLOGY_OUTLINED), self._card("Device", self.device.kind.value, ft.Icons.DEVICES_OUTLINED, self.device.machine)], spacing=12, run_spacing=12)
        feature_lines = []
        for x in self.feature_results.values():
            color = SUCCESS if x.state is FeatureLoadState.ENABLED else ERROR
            feature_lines.append(ft.Row([ft.Container(width=8,height=8,border_radius=99,bgcolor=color), ft.Text(f"{x.spec.label} · {x.state.value.upper()} · {x.detail}", color=MUTED, size=11, expand=True)]))
        return self._body([self._title("Dashboard", "Runtime overview dan health Senna"), cards, self._panel(ft.Column([ft.Text("Core runtime", color=TEXT, weight=ft.FontWeight.W_600), ft.Text(r.summary(), color=MUTED, size=11), ft.Text("Action tools · " + (", ".join(r.action_tools) or "none"), color=MUTED, size=11)])), self._panel(ft.Column([ft.Text("Feature health", color=TEXT, weight=ft.FontWeight.W_600), *feature_lines], spacing=10))])

    async def _chat_guild_changed(self, e: Any) -> None:
        g = self.ctx.client.get_guild(int(self.chat_guild.value)) if self.chat_guild.value else None
        cs = list(g.text_channels) if g else []; self.chat_channel.options = self._options([(c.id, f"#{c.name}") for c in cs]); self.chat_channel.value = str(cs[0].id) if cs else None
        if self.page: self.page.update()
    async def _send_chat(self, e: Any) -> None:
        value = (self.chat_input.value or "").strip()
        if not value or not self.chat_channel.value: return
        c = self.ctx.client.get_channel(int(self.chat_channel.value))
        try:
            if not isinstance(c, discord.TextChannel): raise ValueError("Channel tidak valid")
            await c.send(value); self._chat_lines.append(f"Senna · #{c.name}\n{value}"); self.chat_input.value = ""
        except Exception as ex: self._chat_lines.append(f"SYSTEM\n{type(ex).__name__}: {ex}")
        self.chat_view.value = "\n\n".join(self._chat_lines)
        if self.page: self.page.update()
    async def _clear_chat(self, e: Any) -> None:
        self._chat_lines.clear(); self.chat_view.value = ""
        if self.page: self.page.update()
    def _terminal_chat(self) -> ft.Control:
        self.chat_guild.options = self._guild_options()
        if self.chat_guild.value is None and self.ctx.client.guilds:
            g=self.ctx.client.guilds[0]; self.chat_guild.value=str(g.id); self.chat_channel.options=self._options([(c.id,f"#{c.name}") for c in g.text_channels]); self.chat_channel.value=str(g.text_channels[0].id) if g.text_channels else None
        self.chat_view.value="\n\n".join(self._chat_lines)
        return self._body([self._title("Terminal Chat","Kirim dan pantau Discord dari control center"), ft.ResponsiveRow([ft.Container(col={"xs":12,"md":6},content=self.chat_guild),ft.Container(col={"xs":12,"md":6},content=self.chat_channel)]), ft.Container(height=420,content=self._panel(self.chat_view,expand=True,padding=10)), ft.Row([self.chat_input,ft.IconButton(icon=ft.Icons.SEND_ROUNDED,on_click=self._send_chat),ft.IconButton(icon=ft.Icons.DELETE_SWEEP_OUTLINED,on_click=self._clear_chat)])])

    def _refresh_emoji_list(self) -> None:
        g=self.ctx.client.get_guild(int(self.emoji_guild.value)) if self.emoji_guild.value else None
        self.emoji_text.value="\n".join(f"{x.name} · id={x.id} · {'animated' if x.animated else 'static'}" for x in g.emojis) if g else "Pilih server."
    async def _emoji_guild_changed(self,e:Any)->None:
        self._refresh_emoji_list()
        if self.page:self.page.update()
    async def _refresh_emoji(self,e:Any)->None: await self._emoji_guild_changed(e)
    def _emoji(self)->ft.Control:
        self.emoji_guild.options=self._guild_options()
        if self.emoji_guild.value is None and self.ctx.client.guilds:self.emoji_guild.value=str(self.ctx.client.guilds[0].id)
        self._refresh_emoji_list()
        return self._body([self._title("Emoji","Inventory custom emoji Discord"),ft.Row([self.emoji_guild,ft.IconButton(icon=ft.Icons.REFRESH,on_click=self._refresh_emoji)]),ft.Container(height=500,content=self._panel(ft.Column([self.emoji_text],scroll=ft.ScrollMode.AUTO,expand=True),expand=True,padding=12))])

    async def _voice_guild_changed(self,e:Any)->None:
        g=self.ctx.client.get_guild(int(self.voice_guild.value)) if self.voice_guild.value else None; cs=list(g.voice_channels) if g else []
        self.voice_channel.options=self._options([(c.id,c.name) for c in cs]);self.voice_channel.value=str(cs[0].id) if cs else None
        if self.page:self.page.update()
    async def _voice_join(self,e:Any)->None:
        if not self.voice_channel.value:return
        c=self.ctx.client.get_channel(int(self.voice_channel.value))
        try:
            if not isinstance(c,discord.VoiceChannel):raise ValueError("Voice channel tidak valid")
            v=c.guild.voice_client
            if v and v.is_connected():
                if not v.channel or v.channel.id!=c.id:await v.move_to(c)
            else:await c.connect()
            self.voice_status.value=f"Connected · {c.name}";self.voice_status.color=SUCCESS
        except Exception as ex:self.voice_status.value=f"Join gagal · {type(ex).__name__}: {ex}";self.voice_status.color=ERROR
        if self.page:self.page.update()
    async def _voice_leave(self,e:Any)->None:
        g=self.ctx.client.get_guild(int(self.voice_guild.value)) if self.voice_guild.value else None
        if g and g.voice_client:await g.voice_client.disconnect(force=False)
        self.voice_status.value="Disconnected";self.voice_status.color=MUTED
        if self.page:self.page.update()
    def _voice(self)->ft.Control:
        self.voice_guild.options=self._guild_options()
        if self.voice_guild.value is None and self.ctx.client.guilds:
            g=self.ctx.client.guilds[0];self.voice_guild.value=str(g.id);self.voice_channel.options=self._options([(c.id,c.name) for c in g.voice_channels]);self.voice_channel.value=str(g.voice_channels[0].id) if g.voice_channels else None
        vf=self.feature_results.get("voice");ok=bool(vf and vf.available);detail=vf.detail if vf else "Voice feature not registered"
        return self._body([self._title("Voice","Voice transport, TTS, STT dan music foundation"),self._panel(ft.Column([ft.Text("Voice backend ready" if ok else "Voice backend degraded",color=SUCCESS if ok else ERROR),ft.Text(detail,color=MUTED,size=11)])),ft.ResponsiveRow([ft.Container(col={"xs":12,"md":6},content=self.voice_guild),ft.Container(col={"xs":12,"md":6},content=self.voice_channel)]),self._panel(ft.Column([self.voice_status,ft.Row([ft.Button("Join",on_click=self._voice_join),ft.Button("Leave",on_click=self._voice_leave)]),ft.Divider(color=BORDER),ft.Text("Music",color=TEXT,weight=ft.FontWeight.W_600),ft.Text("Music player/queue akan memakai voice transport yang sama.",color=MUTED,size=11)]))])

    async def _apply_ai_settings(self,e:Any)->None:
        m=self.ctx.assistant
        if not m:return
        try:
            s=replace(m.settings,provider_name=str(self.ai_provider.value),openrouter_model=(self.ai_openrouter.value or "").strip(),nvidia_nim_model=(self.ai_nvidia.value or "").strip(),max_tokens=int(self.ai_tokens.value or "300"),request_timeout_seconds=float(self.ai_timeout.value or "60"))
            await m.apply_settings(s);save_settings(AI_SETTINGS_FILE,s);self.ai_status.value="AI settings applied & saved.";self.ai_status.color=SUCCESS
        except Exception as ex:self.ai_status.value=f"Apply gagal · {type(ex).__name__}: {ex}";self.ai_status.color=ERROR
        if self.page:self.page.update()
    def _ai_settings(self)->ft.Control:
        s=self.ctx.assistant.settings if self.ctx.assistant else None
        self.ai_provider=ft.Dropdown(label="Provider",value=s.provider_name if s else "nvidia_nim",options=[ft.DropdownOption(key="nvidia_nim",text="NVIDIA NIM"),ft.DropdownOption(key="openrouter",text="OpenRouter")]);self.ai_nvidia=ft.TextField(label="NVIDIA NIM model",value=s.nvidia_nim_model if s else "",border_color=BORDER);self.ai_openrouter=ft.TextField(label="OpenRouter model",value=s.openrouter_model if s else "",border_color=BORDER);self.ai_tokens=ft.TextField(label="Max tokens",value=str(s.max_tokens if s else 300),border_color=BORDER);self.ai_timeout=ft.TextField(label="Request timeout (s)",value=str(s.request_timeout_seconds if s else 60),border_color=BORDER)
        return self._body([self._title("AI Setting","Provider, model dan inference runtime"),self._panel(ft.Column([self.ai_provider,self.ai_nvidia,self.ai_openrouter,ft.ResponsiveRow([ft.Container(col={"xs":12,"md":6},content=self.ai_tokens),ft.Container(col={"xs":12,"md":6},content=self.ai_timeout)]),ft.Row([ft.Button("Apply settings",on_click=self._apply_ai_settings),self.ai_status])],spacing=12))])

    async def _refresh_logs(self,e:Any=None)->None:
        with self._log_lock:self.log_text.value="\n".join(self._logs) or "Belum ada log runtime."
        if self.page:self.page.update()
    async def _clear_logs(self,e:Any)->None:
        with self._log_lock:self._logs.clear()
        await self._refresh_logs()
    async def _log_pump(self)->None:
        while self.page is not None:
            if self._selected_index==5:await self._refresh_logs()
            await asyncio.sleep(.8)
    def _settings(self)->ft.Control:
        with self._log_lock:self.log_text.value="\n".join(self._logs) or "Belum ada log runtime."
        web=f"0.0.0.0:{WEB_PORT} · local 127.0.0.1:{WEB_PORT}" if self.device.is_android else "Desktop Flet app"
        log_box=ft.Container(height=500 if self._compact else 620,bgcolor="#080808",border=ft.Border.all(1,BORDER),border_radius=14,padding=14,content=self.log_scroll)
        return self._body([self._title("Settings","Runtime, network dan logs"),self._panel(ft.Row([ft.Text("Live runtime logs",color=TEXT,weight=ft.FontWeight.W_600,expand=True),ft.IconButton(icon=ft.Icons.REFRESH,on_click=self._refresh_logs),ft.IconButton(icon=ft.Icons.DELETE_OUTLINE,on_click=self._clear_logs)])),log_box,self._panel(ft.Column([ft.Text("Runtime endpoint",color=TEXT,weight=ft.FontWeight.W_600),ft.Text(web,color=MUTED,size=11),ft.Text(self.runtime_status.summary(),color=MUTED,size=11),ft.Text(f"Python {self.device.python_version} · {self.device.machine}",color=MUTED,size=11)]))])

    def _view_for_index(self,index:int)->ft.Control:return [self._dashboard,self._terminal_chat,self._emoji,self._voice,self._ai_settings,self._settings][index]()
    async def _nav_changed(self,e:Any)->None:
        self._selected_index=int(e.control.selected_index);self.content.content=self._view_for_index(self._selected_index)
        if self.page:self.page.update()
    def _nav(self)->ft.NavigationRail:
        return ft.NavigationRail(selected_index=self._selected_index,extended=not self._compact,width=78 if self._compact else 220,min_width=72,min_extended_width=220,bgcolor=SIDEBAR,indicator_color="#202020",on_change=self._nav_changed,leading=ft.Container(padding=12,content=ft.Text("SENNA" if not self._compact else "S",color=TEXT,weight=ft.FontWeight.BOLD)),destinations=[ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED,label="Dashboard"),ft.NavigationRailDestination(icon=ft.Icons.FORUM_OUTLINED,label="Terminal Chat"),ft.NavigationRailDestination(icon=ft.Icons.EMOJI_EMOTIONS_OUTLINED,label="Emoji"),ft.NavigationRailDestination(icon=ft.Icons.GRAPHIC_EQ_OUTLINED,label="Voice"),ft.NavigationRailDestination(icon=ft.Icons.PSYCHOLOGY_OUTLINED,label="AI Setting"),ft.NavigationRailDestination(icon=ft.Icons.SETTINGS_OUTLINED,label="Settings")])
    async def main(self,page:ft.Page)->None:
        self.page=page;self._compact=bool((page.width or 1200)<820);page.title="Senna Control Center";page.theme_mode=ft.ThemeMode.DARK;page.bgcolor=BG;page.padding=0;page.spacing=0;page.theme=ft.Theme(color_scheme_seed="#AFAFAF");self.content.content=self._dashboard();page.add(ft.Row([self._nav(),ft.VerticalDivider(width=1,color=BORDER),self.content],expand=True,spacing=0));page.run_task(self._log_pump);print(f"[SENA UI] Browser connected; dashboard ready mode={'web' if self.device.is_android else 'desktop'}")
    async def run(self)->None:
        self.install_log_capture();view=ft.AppView.WEB_BROWSER if self.device.is_android else ft.AppView.FLET_APP
        try:
            if self.device.is_android:
                print(f"[SENA UI] Starting web server host={WEB_HOST} port={WEB_PORT}");print(f"[SENA UI] Open on this phone: http://127.0.0.1:{WEB_PORT}");print(f"[SENA UI] Open from laptop: http://<PHONE-LAN-IP>:{WEB_PORT}");await ft.run_async(self.main,view=view,host=WEB_HOST,port=WEB_PORT)
            else:await ft.run_async(self.main,view=view)
        finally:self.page=None;self.restore_log_capture()
