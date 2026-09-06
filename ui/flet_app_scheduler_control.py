from __future__ import annotations

import asyncio
from typing import Any

import flet as ft

from scheduler.control import ScheduleBucket, classify_job, list_jobs, retry_failed
from ui.flet_app import BORDER, ERROR, MUTED, SUCCESS, TEXT, WARNING
from ui.flet_app_voice_split import SenaFletUI as _BaseSenaFletUI


_BUCKET_LABELS = {
    ScheduleBucket.UPCOMING: "UPCOMING",
    ScheduleBucket.RECURRING: "RECURRING",
    ScheduleBucket.FAILED: "FAILED",
    ScheduleBucket.COMPLETED: "COMPLETED",
    ScheduleBucket.INACTIVE: "INACTIVE",
}


class SenaFletUI(_BaseSenaFletUI):
    """Scheduler control center with failed-job recovery and history views."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.schedule_cancel.label = "Job terpilih"
        self.schedule_filter = ft.Dropdown(
            label="Filter",
            value="all",
            options=self._options(
                [
                    ("all", "Semua"),
                    (ScheduleBucket.UPCOMING.value, "Upcoming"),
                    (ScheduleBucket.RECURRING.value, "Recurring"),
                    (ScheduleBucket.FAILED.value, "Failed"),
                    (ScheduleBucket.COMPLETED.value, "Completed"),
                    (ScheduleBucket.INACTIVE.value, "Inactive / Cancelled"),
                ]
            ),
            on_select=self._schedule_filter_changed,
        )
        self.schedule_counts = ft.Text(
            "Upcoming 0 · Recurring 0 · Failed 0 · Completed 0",
            color=MUTED,
            size=11,
        )
        self._schedule_last_refresh = 0.0

    async def _schedule_filter_changed(self, e: Any) -> None:
        del e
        await self._refresh_schedule()

    def _schedule_item_label(self, item: Any) -> str:
        bucket = classify_job(item)
        state = _BUCKET_LABELS[bucket]
        time_value = (
            item.failed_at
            if bucket is ScheduleBucket.FAILED and item.failed_at
            else item.last_run_at
            if bucket is ScheduleBucket.COMPLETED and item.last_run_at
            else item.next_run_at
        )
        return (
            f"#{item.id} · {state} · {item.job_type} · "
            f"{self._schedule_local_time(time_value)}"
        )

    async def _refresh_schedule(self, e: Any = None) -> None:
        del e
        scheduler = self.ctx.scheduler
        if scheduler is None or not scheduler.available:
            self.schedule_list.value = "Scheduler offline."
            self.schedule_cancel.options = []
            self.schedule_cancel.value = None
            self.schedule_counts.value = (
                "Upcoming 0 · Recurring 0 · Failed 0 · Completed 0"
            )
            if self.page:
                self.page.update()
            return

        try:
            items = await list_jobs(
                scheduler,
                self._schedule_creator_id(),
                include_all=True,
                limit=250,
            )
            counts = {bucket: 0 for bucket in ScheduleBucket}
            for item in items:
                counts[classify_job(item)] += 1

            self.schedule_counts.value = (
                f"Upcoming {counts[ScheduleBucket.UPCOMING]} · "
                f"Recurring {counts[ScheduleBucket.RECURRING]} · "
                f"Failed {counts[ScheduleBucket.FAILED]} · "
                f"Completed {counts[ScheduleBucket.COMPLETED]} · "
                f"Inactive {counts[ScheduleBucket.INACTIVE]}"
            )

            self.schedule_cancel.options = self._options(
                [(item.id, self._schedule_item_label(item)) for item in items]
            )
            valid = {str(item.id) for item in items}
            if self.schedule_cancel.value not in valid:
                self.schedule_cancel.value = str(items[0].id) if items else None

            selected_filter = str(self.schedule_filter.value or "all")
            visible = [
                item
                for item in items
                if selected_filter == "all"
                or classify_job(item).value == selected_filter
            ]

            lines: list[str] = []
            for item in visible:
                bucket = classify_job(item)
                repeat = (
                    f" · every={item.recurrence_seconds}s"
                    if item.recurrence_seconds is not None
                    else ""
                )
                retry = (
                    f" · retry={item.retry_count}/{item.max_retries}"
                    if item.retry_count or item.last_error
                    else f" · max_retries={item.max_retries}"
                )
                runs = f" · runs={item.run_count}" if item.run_count else ""
                error = f"\n    last_error: {item.last_error}" if item.last_error else ""
                preview = self._schedule_payload_preview(item)
                timestamp = (
                    item.failed_at
                    if bucket is ScheduleBucket.FAILED and item.failed_at
                    else item.last_run_at
                    if bucket is ScheduleBucket.COMPLETED and item.last_run_at
                    else item.next_run_at
                )
                lines.append(
                    f"#{item.id} · {_BUCKET_LABELS[bucket]} · {item.job_type} · "
                    f"{self._schedule_local_time(timestamp)}{repeat}{retry}{runs}\n"
                    f"    {preview}{error}"
                )

            self.schedule_list.value = (
                "\n\n".join(lines)
                if lines
                else "Tidak ada job untuk filter ini."
            )
        except Exception as error:
            self.schedule_list.value = (
                f"Refresh gagal · {type(error).__name__}: {error}"
            )

        if self.page:
            self.page.update()

    def _selected_schedule_id(self) -> int:
        if not self.schedule_cancel.value:
            raise ValueError("Pilih job terlebih dahulu.")
        return int(self.schedule_cancel.value)

    async def _cancel_schedule(self, e: Any) -> None:
        del e
        scheduler = self.ctx.scheduler
        try:
            if scheduler is None or not scheduler.available:
                raise RuntimeError("Scheduler tidak aktif.")
            schedule_id = self._selected_schedule_id()
            changed = await scheduler.cancel(
                schedule_id,
                self._schedule_creator_id(),
                is_owner=True,
            )
            self.schedule_status.value = (
                f"Schedule #{schedule_id} dibatalkan."
                if changed
                else f"Schedule #{schedule_id} bukan job aktif."
            )
            self.schedule_status.color = SUCCESS if changed else WARNING
        except Exception as error:
            self.schedule_status.value = (
                f"Cancel gagal · {type(error).__name__}: {error}"
            )
            self.schedule_status.color = ERROR
        await self._refresh_schedule()

    async def _run_schedule_now(self, e: Any) -> None:
        del e
        scheduler = self.ctx.scheduler
        try:
            if scheduler is None or not scheduler.available:
                raise RuntimeError("Scheduler tidak aktif.")
            schedule_id = self._selected_schedule_id()
            changed = await scheduler.run_now(
                schedule_id,
                self._schedule_creator_id(),
                is_owner=True,
            )
            self.schedule_status.value = (
                f"Schedule #{schedule_id} diset untuk run now."
                if changed
                else f"Schedule #{schedule_id} bukan job aktif."
            )
            self.schedule_status.color = SUCCESS if changed else WARNING
        except Exception as error:
            self.schedule_status.value = (
                f"Run now gagal · {type(error).__name__}: {error}"
            )
            self.schedule_status.color = ERROR
        await self._refresh_schedule()

    async def _retry_failed_schedule(self, e: Any) -> None:
        del e
        scheduler = self.ctx.scheduler
        try:
            if scheduler is None or not scheduler.available:
                raise RuntimeError("Scheduler tidak aktif.")
            schedule_id = self._selected_schedule_id()
            changed = await retry_failed(
                scheduler,
                schedule_id,
                self._schedule_creator_id(),
                is_owner=True,
            )
            self.schedule_status.value = (
                f"FAILED job #{schedule_id} diaktifkan ulang dan akan dicoba sekarang."
                if changed
                else f"Schedule #{schedule_id} bukan job FAILED."
            )
            self.schedule_status.color = SUCCESS if changed else WARNING
        except Exception as error:
            self.schedule_status.value = (
                f"Retry gagal · {type(error).__name__}: {error}"
            )
            self.schedule_status.color = ERROR
        await self._refresh_schedule()

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

        scheduler = self.ctx.scheduler
        registered_jobs = (
            ", ".join(scheduler.job_types)
            if scheduler is not None and scheduler.job_types
            else "none"
        )

        return self._body(
            [
                self._title(
                    "Scheduler",
                    "Persistent jobs, history, recovery, dan runtime control",
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        "Scheduler runtime",
                                        color=TEXT,
                                        weight=ft.FontWeight.W_600,
                                        expand=True,
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.REFRESH,
                                        on_click=self._refresh_schedule,
                                    ),
                                ]
                            ),
                            ft.Text(
                                "ONLINE"
                                if scheduler is not None and scheduler.available
                                else "OFFLINE",
                                color=(
                                    SUCCESS
                                    if scheduler is not None and scheduler.available
                                    else ERROR
                                ),
                                weight=ft.FontWeight.W_600,
                            ),
                            self.schedule_counts,
                            ft.Text(
                                "Registered jobs · " + registered_jobs,
                                color=MUTED,
                                size=10,
                                selectable=True,
                            ),
                        ],
                        spacing=7,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text(
                                "Create discord.message",
                                color=TEXT,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(
                                        col={"xs": 12, "md": 6},
                                        content=self.schedule_guild,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 6},
                                        content=self.schedule_channel,
                                    ),
                                ]
                            ),
                            self.schedule_message,
                            self.schedule_mention,
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(
                                        col={"xs": 12, "md": 6},
                                        content=self.schedule_run_at,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 6},
                                        content=self.schedule_delay,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 6},
                                        content=self.schedule_repeat,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 6},
                                        content=self.schedule_max_retries,
                                    ),
                                ]
                            ),
                            ft.Text(
                                "Run at mengalahkan delay. Repeat minimal 60 detik. "
                                "Job universal lain tetap dapat dibuat melalui Action System.",
                                color=MUTED,
                                size=10,
                            ),
                            ft.Button(
                                "Create message schedule",
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
                            ft.Text(
                                "Control Center",
                                color=TEXT,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(
                                        col={"xs": 12, "md": 5},
                                        content=self.schedule_filter,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 7},
                                        content=self.schedule_cancel,
                                    ),
                                ]
                            ),
                            ft.Row(
                                wrap=True,
                                controls=[
                                    ft.Button(
                                        "Run Now",
                                        icon=ft.Icons.PLAY_ARROW,
                                        on_click=self._run_schedule_now,
                                    ),
                                    ft.Button(
                                        "Retry Failed",
                                        icon=ft.Icons.RESTART_ALT,
                                        on_click=self._retry_failed_schedule,
                                    ),
                                    ft.Button(
                                        "Cancel Active",
                                        icon=ft.Icons.DELETE_OUTLINE,
                                        on_click=self._cancel_schedule,
                                    ),
                                ],
                            ),
                            ft.Text(
                                "Run Now hanya untuk job aktif. Retry Failed mengaktifkan "
                                "kembali job terminally failed, reset retry counter, lalu "
                                "menjadwalkannya segera.",
                                color=MUTED,
                                size=10,
                            ),
                            ft.Container(
                                height=360 if self._compact else 500,
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

    async def _log_pump(self) -> None:
        while self.page is not None:
            if self._selected_index == 4:
                await self._music_refresh()
            elif self._selected_index == 6:
                now = asyncio.get_running_loop().time()
                if now - self._schedule_last_refresh >= 2.0:
                    self._schedule_last_refresh = now
                    await self._refresh_schedule()
            elif self._selected_index == 7:
                await self._refresh_logs()
            await asyncio.sleep(0.6)
