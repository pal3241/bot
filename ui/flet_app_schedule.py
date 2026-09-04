from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import flet as ft

from ui.flet_app import BORDER, ERROR, MUTED, SUCCESS, TEXT
from ui.flet_app_html_upload import SenaFletUI as _BaseSenaFletUI


class SenaFletUI(_BaseSenaFletUI):
    """Control center with persistent scheduler management."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.schedule_guild = ft.Dropdown(
            label="Server",
            expand=True,
            on_select=self._schedule_guild_changed,
        )
        self.schedule_channel = ft.Dropdown(label="Channel", expand=True)
        self.schedule_message = ft.TextField(
            label="Pesan yang akan dikirim",
            multiline=True,
            min_lines=2,
            max_lines=5,
            border_color=BORDER,
        )
        self.schedule_mention = ft.TextField(
            label="Tag user ID (opsional)",
            hint_text="contoh: 123456789012345678",
            border_color=BORDER,
        )
        self.schedule_run_at = ft.TextField(
            label="Run at ISO-8601 (opsional)",
            hint_text="2026-09-04T20:00:00+07:00",
            border_color=BORDER,
        )
        self.schedule_delay = ft.TextField(
            label="Atau delay menit",
            value="10",
            border_color=BORDER,
        )
        self.schedule_repeat = ft.TextField(
            label="Repeat tiap N menit (opsional)",
            hint_text="kosong = sekali jalan",
            border_color=BORDER,
        )
        self.schedule_cancel = ft.Dropdown(label="Schedule aktif", expand=True)
        self.schedule_status = ft.Text("", size=11, color=MUTED)
        self.schedule_list = ft.Text(
            "Belum dimuat.",
            size=11,
            color="#D8D8D8",
            selectable=True,
        )

    def _schedule_creator_id(self) -> int:
        assistant = self.ctx.assistant
        if assistant is not None and assistant.owner_resolver.owner_id is not None:
            return int(assistant.owner_resolver.owner_id)
        if self.ctx.client.user is not None:
            return int(self.ctx.client.user.id)
        raise RuntimeError("Owner/bot ID belum tersedia.")

    def _schedule_local_time(self, value: str) -> str:
        timezone_name = os.getenv("SENA_TIMEZONE", "Asia/Jakarta").strip() or "Asia/Jakarta"
        try:
            zone = ZoneInfo(timezone_name)
        except Exception:
            zone = ZoneInfo("UTC")
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S %Z")

    async def _schedule_guild_changed(self, e: Any) -> None:
        del e
        guild = (
            self.ctx.client.get_guild(int(self.schedule_guild.value))
            if self.schedule_guild.value
            else None
        )
        channels = list(guild.text_channels) if guild else []
        self.schedule_channel.options = self._options(
            [(channel.id, f"#{channel.name}") for channel in channels]
        )
        self.schedule_channel.value = str(channels[0].id) if channels else None
        if self.page:
            self.page.update()

    async def _create_schedule(self, e: Any) -> None:
        del e
        scheduler = self.ctx.scheduler
        if scheduler is None or not scheduler.available:
            self.schedule_status.value = "Scheduler tidak aktif."
            self.schedule_status.color = ERROR
            if self.page:
                self.page.update()
            return
        try:
            if not self.schedule_channel.value:
                raise ValueError("Pilih channel tujuan.")
            message = (self.schedule_message.value or "").strip()
            if not message:
                raise ValueError("Pesan schedule kosong.")

            mention_raw = (self.schedule_mention.value or "").strip()
            mention_user_id = int(mention_raw) if mention_raw else None
            run_at = (self.schedule_run_at.value or "").strip() or None
            delay_raw = (self.schedule_delay.value or "").strip()
            delay_seconds = None if run_at else float(delay_raw) * 60.0
            repeat_raw = (self.schedule_repeat.value or "").strip()
            recurrence_seconds = int(float(repeat_raw) * 60) if repeat_raw else None

            guild_id = int(self.schedule_guild.value) if self.schedule_guild.value else None
            item = await scheduler.create(
                guild_id=guild_id,
                channel_id=int(self.schedule_channel.value),
                creator_id=self._schedule_creator_id(),
                content=message,
                mention_user_id=mention_user_id,
                run_at=run_at,
                delay_seconds=delay_seconds,
                recurrence_seconds=recurrence_seconds,
            )
            tag = f" · tag=<@{item.mention_user_id}>" if item.mention_user_id else ""
            self.schedule_status.value = (
                f"Schedule #{item.id} dibuat · {self._schedule_local_time(item.next_run_at)}{tag}"
            )
            self.schedule_status.color = SUCCESS
            await self._refresh_schedule()
        except Exception as error:
            self.schedule_status.value = f"Create gagal · {type(error).__name__}: {error}"
            self.schedule_status.color = ERROR
        if self.page:
            self.page.update()

    async def _refresh_schedule(self, e: Any = None) -> None:
        del e
        scheduler = self.ctx.scheduler
        if scheduler is None or not scheduler.available:
            self.schedule_list.value = "Scheduler offline."
            self.schedule_cancel.options = []
            self.schedule_cancel.value = None
            if self.page:
                self.page.update()
            return
        try:
            items = await scheduler.list_for_user(
                self._schedule_creator_id(),
                include_all=True,
            )
            self.schedule_cancel.options = self._options(
                [
                    (
                        item.id,
                        f"#{item.id} · {self._schedule_local_time(item.next_run_at)}",
                    )
                    for item in items
                ]
            )
            valid = {str(item.id) for item in items}
            if self.schedule_cancel.value not in valid:
                self.schedule_cancel.value = str(items[0].id) if items else None

            lines: list[str] = []
            for item in items:
                tag = f" · tag=<@{item.mention_user_id}>" if item.mention_user_id else ""
                repeat = (
                    f" · repeat={item.recurrence_seconds // 60}m"
                    if item.recurrence_seconds
                    else ""
                )
                preview = item.content.replace("\n", " ")
                if len(preview) > 90:
                    preview = preview[:87] + "..."
                lines.append(
                    f"#{item.id} · {self._schedule_local_time(item.next_run_at)}{tag}{repeat} · {preview}"
                )
            self.schedule_list.value = "\n".join(lines) or "Tidak ada schedule aktif."
        except Exception as error:
            self.schedule_list.value = f"Refresh gagal · {type(error).__name__}: {error}"
        if self.page:
            self.page.update()

    async def _cancel_schedule(self, e: Any) -> None:
        del e
        scheduler = self.ctx.scheduler
        if scheduler is None or not scheduler.available:
            self.schedule_status.value = "Scheduler tidak aktif."
            self.schedule_status.color = ERROR
        elif not self.schedule_cancel.value:
            self.schedule_status.value = "Pilih schedule yang akan dibatalkan."
            self.schedule_status.color = ERROR
        else:
            try:
                schedule_id = int(self.schedule_cancel.value)
                cancelled = await scheduler.cancel(
                    schedule_id,
                    self._schedule_creator_id(),
                    is_owner=True,
                )
                self.schedule_status.value = (
                    f"Schedule #{schedule_id} dibatalkan."
                    if cancelled
                    else f"Schedule #{schedule_id} sudah tidak aktif."
                )
                self.schedule_status.color = SUCCESS if cancelled else MUTED
                await self._refresh_schedule()
            except Exception as error:
                self.schedule_status.value = f"Cancel gagal · {type(error).__name__}: {error}"
                self.schedule_status.color = ERROR
        if self.page:
            self.page.update()

    def _schedule(self) -> ft.Control:
        self.schedule_guild.options = self._guild_options()
        if self.schedule_guild.value is None and self.ctx.client.guilds:
            guild = self.ctx.client.guilds[0]
            self.schedule_guild.value = str(guild.id)
            self.schedule_channel.options = self._options(
                [(channel.id, f"#{channel.name}") for channel in guild.text_channels]
            )
            self.schedule_channel.value = (
                str(guild.text_channels[0].id) if guild.text_channels else None
            )

        if self.page:
            self.page.run_task(self._refresh_schedule)

        return self._body(
            [
                self._title(
                    "Schedule",
                    "Pesan terjadwal, repeat, channel target, dan user mention",
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.schedule_guild),
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.schedule_channel),
                                ]
                            ),
                            self.schedule_message,
                            self.schedule_mention,
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.schedule_run_at),
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.schedule_delay),
                                    ft.Container(col={"xs": 12, "md": 6}, content=self.schedule_repeat),
                                ]
                            ),
                            ft.Text(
                                "Kalau Run at diisi, Delay menit diabaikan. Timezone default mengikuti SENA_TIMEZONE (Asia/Jakarta). Tag memakai Discord user ID.",
                                color=MUTED,
                                size=10,
                            ),
                            ft.Button(
                                "Create schedule",
                                icon=ft.Icons.SCHEDULE,
                                on_click=self._create_schedule,
                            ),
                            self.schedule_status,
                        ],
                        spacing=12,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text("Active schedules", color=TEXT, weight=ft.FontWeight.W_600, expand=True),
                                    ft.IconButton(icon=ft.Icons.REFRESH, on_click=self._refresh_schedule),
                                ]
                            ),
                            self.schedule_cancel,
                            ft.Button(
                                "Cancel selected",
                                icon=ft.Icons.DELETE_OUTLINE,
                                on_click=self._cancel_schedule,
                            ),
                            ft.Container(
                                height=300 if self._compact else 380,
                                padding=12,
                                bgcolor="#080808",
                                border=ft.Border.all(1, BORDER),
                                border_radius=12,
                                content=ft.Column(
                                    controls=[self.schedule_list],
                                    scroll=ft.ScrollMode.AUTO,
                                ),
                            ),
                        ],
                        spacing=10,
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
            self._ai_settings,
            self._schedule,
            self._settings,
        ]
        return builders[index]()

    def _nav(self) -> ft.NavigationRail:
        rail = super()._nav()
        rail.destinations.insert(
            5,
            ft.NavigationRailDestination(
                icon=ft.Icons.SCHEDULE,
                label="Schedule",
            ),
        )
        return rail

    async def _log_pump(self) -> None:
        while self.page is not None:
            if self._selected_index == 6:
                await self._refresh_logs()
            await asyncio.sleep(0.8)
