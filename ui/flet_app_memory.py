from __future__ import annotations

import asyncio
from typing import Any

import flet as ft

from memory.control import (
    create_memory,
    delete_memory,
    list_memories,
    set_memory_pinned,
    update_memory,
)
from memory.identity import UserIdentity
from memory.models import MEMORY_CATEGORIES, MemoryRecord
from ui.flet_app import BORDER, ERROR, MUTED, SUCCESS, TEXT, WARNING
from ui.flet_app_scheduler_control import SenaFletUI as _BaseSenaFletUI


class SenaFletUI(_BaseSenaFletUI):
    """Owner-only Memory Control Center layered on top of the existing Flet UI."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.memory_search = ft.TextField(
            label="Search memory",
            hint_text="Cari isi, category, atau source...",
            border_color=BORDER,
            on_submit=self._memory_refresh,
        )
        self.memory_filter_category = ft.Dropdown(
            label="Category",
            value="all",
            options=self._options(
                [("all", "Semua"), *[(item, item.title()) for item in sorted(MEMORY_CATEGORIES)]]
            ),
            on_select=self._memory_filter_changed,
        )
        self.memory_pinned_only = ft.Switch(
            label="Pinned only",
            value=False,
            on_change=self._memory_filter_changed,
        )
        self.memory_selector = ft.Dropdown(
            label="Memory terpilih",
            options=[],
            on_select=self._memory_selected,
            expand=True,
        )
        self.memory_stats = ft.Text("Memory belum dimuat.", color=MUTED, size=11)
        self.memory_list = ft.Text(
            "Belum dimuat.",
            size=11,
            color="#D8D8D8",
            selectable=True,
        )
        self.memory_category = ft.Dropdown(
            label="Category",
            value="fact",
            options=self._options([(item, item.title()) for item in sorted(MEMORY_CATEGORIES)]),
        )
        self.memory_content = ft.TextField(
            label="Content",
            hint_text="Informasi yang perlu Sena ingat...",
            multiline=True,
            min_lines=3,
            max_lines=7,
            border_color=BORDER,
        )
        self.memory_importance = ft.TextField(
            label="Importance 0..1",
            value="0.85",
            border_color=BORDER,
        )
        self.memory_confidence = ft.TextField(
            label="Confidence 0..1",
            value="0.95",
            border_color=BORDER,
        )
        self.memory_pinned = ft.Switch(label="Pinned / priority retrieval", value=False)
        self.memory_metadata = ft.Text(
            "New memory · source akan menjadi flet_memory_control",
            color=MUTED,
            size=10,
            selectable=True,
        )
        self.memory_status = ft.Text("", color=MUTED, size=11)
        self._memory_records: dict[int, MemoryRecord] = {}
        self._memory_delete_armed_id: int | None = None

    def _memory_identity(self) -> UserIdentity:
        assistant = self.ctx.assistant
        if assistant is None:
            raise RuntimeError("AI Assistant tidak tersedia.")
        owner_id = assistant.owner_resolver.owner_id
        if owner_id is None:
            raise RuntimeError("SENA_OWNER_ID belum dikonfigurasi.")
        return assistant.owner_resolver.resolve(int(owner_id), "Owner")

    def _memory_manager(self):
        assistant = self.ctx.assistant
        if assistant is None or not assistant.memory.available:
            raise RuntimeError("Memory Manager tidak aktif.")
        return assistant.memory

    def _selected_memory_id(self) -> int | None:
        value = self.memory_selector.value
        if value is None or not str(value).strip():
            return None
        return int(str(value))

    @staticmethod
    def _memory_preview(record: MemoryRecord, limit: int = 90) -> str:
        clean = " ".join(record.content.split())
        return clean if len(clean) <= limit else clean[: limit - 3] + "..."

    def _memory_label(self, record: MemoryRecord) -> str:
        pin = "PIN · " if record.pinned else ""
        return f"#{record.id} · {pin}{record.category} · {self._memory_preview(record, 56)}"

    async def _memory_filter_changed(self, e: Any = None) -> None:
        del e
        await self._memory_refresh()

    async def _memory_refresh(self, e: Any = None) -> None:
        del e
        try:
            manager = self._memory_manager()
            identity = self._memory_identity()
            selected_category = str(self.memory_filter_category.value or "all")
            category = None if selected_category == "all" else selected_category
            records = await list_memories(
                manager,
                identity.user_id,
                query=str(self.memory_search.value or ""),
                category=category,
                pinned_only=bool(self.memory_pinned_only.value),
            )
            self._memory_records = {record.id: record for record in records}
            self.memory_selector.options = self._options(
                [(record.id, self._memory_label(record)) for record in records]
            )
            valid = {str(record.id) for record in records}
            if self.memory_selector.value not in valid:
                self.memory_selector.value = None

            all_records = await manager.list_memories(identity.user_id)
            pinned_count = sum(1 for record in all_records if record.pinned)
            category_counts: dict[str, int] = {}
            for record in all_records:
                category_counts[record.category] = category_counts.get(record.category, 0) + 1
            category_summary = " · ".join(
                f"{key}={value}" for key, value in sorted(category_counts.items())
            )
            self.memory_stats.value = (
                f"Active {len(all_records)} · Pinned {pinned_count} · "
                f"Visible {len(records)}"
                + (f"\n{category_summary}" if category_summary else "")
            )

            lines: list[str] = []
            for record in records:
                pin = "📌 " if record.pinned else ""
                lines.append(
                    f"{pin}#{record.id} · {record.category} · "
                    f"importance={record.importance:.2f} · confidence={record.confidence:.2f} · "
                    f"access={record.access_count}\n"
                    f"    {record.content}\n"
                    f"    source={record.source} · updated={record.updated_at}"
                )
            self.memory_list.value = "\n\n".join(lines) or "Tidak ada memory untuk filter ini."
            self.memory_status.value = "Memory list diperbarui."
            self.memory_status.color = MUTED
        except Exception as error:
            self.memory_list.value = f"Memory unavailable · {type(error).__name__}: {error}"
            self.memory_stats.value = "Memory unavailable"
            self.memory_status.value = f"Refresh gagal · {type(error).__name__}: {error}"
            self.memory_status.color = ERROR
        if self.page:
            self.page.update()

    async def _memory_selected(self, e: Any = None) -> None:
        del e
        self._memory_delete_armed_id = None
        memory_id = self._selected_memory_id()
        if memory_id is None:
            self._memory_new_fields()
        else:
            record = self._memory_records.get(memory_id)
            if record is None:
                try:
                    record = await self._memory_manager().get_memory(
                        self._memory_identity().user_id,
                        memory_id,
                    )
                except Exception:
                    record = None
            if record is None or not record.active:
                self.memory_status.value = f"Memory #{memory_id} tidak ditemukan."
                self.memory_status.color = ERROR
            else:
                self.memory_category.value = record.category
                self.memory_content.value = record.content
                self.memory_importance.value = f"{record.importance:.2f}"
                self.memory_confidence.value = f"{record.confidence:.2f}"
                self.memory_pinned.value = record.pinned
                self.memory_metadata.value = (
                    f"#{record.id} · source={record.source} · visibility={record.visibility}\n"
                    f"created={record.created_at} · updated={record.updated_at} · "
                    f"last_accessed={record.last_accessed_at or '-'} · access={record.access_count}"
                )
                self.memory_status.value = f"Memory #{record.id} dimuat ke editor."
                self.memory_status.color = SUCCESS
        if self.page:
            self.page.update()

    def _memory_new_fields(self) -> None:
        self.memory_selector.value = None
        self.memory_category.value = "fact"
        self.memory_content.value = ""
        self.memory_importance.value = "0.85"
        self.memory_confidence.value = "0.95"
        self.memory_pinned.value = False
        self.memory_metadata.value = "New memory · source akan menjadi flet_memory_control"
        self.memory_status.value = "Editor siap untuk memory baru."
        self.memory_status.color = MUTED
        self._memory_delete_armed_id = None

    async def _memory_new(self, e: Any = None) -> None:
        del e
        self._memory_new_fields()
        if self.page:
            self.page.update()

    async def _memory_save(self, e: Any = None) -> None:
        del e
        try:
            manager = self._memory_manager()
            identity = self._memory_identity()
            category = str(self.memory_category.value or "")
            content = str(self.memory_content.value or "")
            importance = str(self.memory_importance.value or "")
            confidence = str(self.memory_confidence.value or "")
            memory_id = self._selected_memory_id()

            if memory_id is None:
                record = await create_memory(
                    manager,
                    identity,
                    category=category,
                    content=content,
                    importance=importance,
                    confidence=confidence,
                    pinned=bool(self.memory_pinned.value),
                )
                self.memory_selector.value = str(record.id)
                self.memory_status.value = f"Memory #{record.id} dibuat."
            else:
                record = await update_memory(
                    manager,
                    identity,
                    memory_id,
                    category=category,
                    content=content,
                    importance=importance,
                    confidence=confidence,
                )
                if record.pinned != bool(self.memory_pinned.value):
                    record = await set_memory_pinned(
                        manager,
                        identity,
                        record.id,
                        bool(self.memory_pinned.value),
                    )
                self.memory_status.value = f"Memory #{record.id} diperbarui."
            self.memory_status.color = SUCCESS
            await self._memory_refresh()
            self.memory_selector.value = str(record.id)
            await self._memory_selected()
        except Exception as error:
            self.memory_status.value = f"Save gagal · {type(error).__name__}: {error}"
            self.memory_status.color = ERROR
            if self.page:
                self.page.update()

    async def _memory_toggle_pin(self, e: Any = None) -> None:
        del e
        try:
            memory_id = self._selected_memory_id()
            if memory_id is None:
                raise ValueError("Pilih memory yang ingin di-pin/unpin.")
            manager = self._memory_manager()
            identity = self._memory_identity()
            current = await manager.get_memory(identity.user_id, memory_id)
            if current is None or not current.active:
                raise LookupError(f"Memory #{memory_id} tidak ditemukan.")
            updated = await set_memory_pinned(
                manager,
                identity,
                memory_id,
                not current.pinned,
            )
            self.memory_status.value = (
                f"Memory #{memory_id} dipin untuk prioritas retrieval."
                if updated.pinned
                else f"Pin memory #{memory_id} dilepas."
            )
            self.memory_status.color = SUCCESS
            await self._memory_refresh()
            self.memory_selector.value = str(memory_id)
            await self._memory_selected()
        except Exception as error:
            self.memory_status.value = f"Pin gagal · {type(error).__name__}: {error}"
            self.memory_status.color = ERROR
            if self.page:
                self.page.update()

    async def _memory_delete(self, e: Any = None) -> None:
        del e
        try:
            memory_id = self._selected_memory_id()
            if memory_id is None:
                raise ValueError("Pilih memory yang ingin dihapus.")
            if self._memory_delete_armed_id != memory_id:
                self._memory_delete_armed_id = memory_id
                self.memory_status.value = (
                    f"Konfirmasi delete memory #{memory_id}: tekan Delete sekali lagi."
                )
                self.memory_status.color = WARNING
                if self.page:
                    self.page.update()
                return

            manager = self._memory_manager()
            identity = self._memory_identity()
            deleted = await delete_memory(manager, identity, memory_id)
            self._memory_delete_armed_id = None
            self.memory_status.value = (
                f"Memory #{memory_id} dihapus (soft delete)."
                if deleted
                else f"Memory #{memory_id} sudah tidak aktif."
            )
            self.memory_status.color = SUCCESS if deleted else WARNING
            self._memory_new_fields()
            await self._memory_refresh()
        except Exception as error:
            self.memory_status.value = f"Delete gagal · {type(error).__name__}: {error}"
            self.memory_status.color = ERROR
            if self.page:
                self.page.update()

    def _memory(self) -> ft.Control:
        if self.page:
            self.page.run_task(self._memory_refresh)
        owner_configured = (
            self.ctx.assistant is not None
            and self.ctx.assistant.owner_resolver.owner_id is not None
        )
        manager_ready = (
            self.ctx.assistant is not None and self.ctx.assistant.memory.available
        )
        return self._body(
            [
                self._title(
                    "Memory",
                    "Owner memory search, editor, pin priority, dan safe delete",
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text(
                                "Memory runtime",
                                color=TEXT,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                "READY" if owner_configured and manager_ready else "UNAVAILABLE",
                                color=SUCCESS if owner_configured and manager_ready else ERROR,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                "Control Center ini sengaja owner-only. Memory ordinary users tidak ditampilkan di panel ini untuk menjaga boundary privacy.",
                                color=MUTED,
                                size=10,
                            ),
                            self.memory_stats,
                        ],
                        spacing=7,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("Search & Browse", color=TEXT, weight=ft.FontWeight.W_600),
                            self.memory_search,
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(
                                        col={"xs": 12, "md": 6},
                                        content=self.memory_filter_category,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 6},
                                        content=self.memory_pinned_only,
                                    ),
                                ]
                            ),
                            ft.Row(
                                wrap=True,
                                controls=[
                                    ft.Button(
                                        "Refresh",
                                        icon=ft.Icons.REFRESH,
                                        on_click=self._memory_refresh,
                                    ),
                                    ft.Button(
                                        "New Memory",
                                        icon=ft.Icons.ADD,
                                        on_click=self._memory_new,
                                    ),
                                ],
                            ),
                            self.memory_selector,
                            ft.Container(
                                height=280 if self._compact else 360,
                                padding=12,
                                bgcolor="#080808",
                                border=ft.Border.all(1, BORDER),
                                border_radius=12,
                                content=ft.Column(
                                    controls=[self.memory_list],
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
                            ft.Text("Memory Editor", color=TEXT, weight=ft.FontWeight.W_600),
                            self.memory_category,
                            self.memory_content,
                            ft.ResponsiveRow(
                                controls=[
                                    ft.Container(
                                        col={"xs": 12, "md": 6},
                                        content=self.memory_importance,
                                    ),
                                    ft.Container(
                                        col={"xs": 12, "md": 6},
                                        content=self.memory_confidence,
                                    ),
                                ]
                            ),
                            self.memory_pinned,
                            ft.Text(
                                "Pinned memberi bonus retrieval priority, tetapi tetap tunduk pada context budget. Create/update tetap melewati Memory Policy Sena.",
                                color=MUTED,
                                size=10,
                            ),
                            self.memory_metadata,
                            ft.Row(
                                wrap=True,
                                controls=[
                                    ft.Button(
                                        "Save",
                                        icon=ft.Icons.SAVE,
                                        on_click=self._memory_save,
                                    ),
                                    ft.Button(
                                        "Pin / Unpin",
                                        icon=ft.Icons.PUSH_PIN,
                                        on_click=self._memory_toggle_pin,
                                    ),
                                    ft.Button(
                                        "Delete",
                                        icon=ft.Icons.DELETE_OUTLINE,
                                        on_click=self._memory_delete,
                                    ),
                                ],
                            ),
                            self.memory_status,
                        ],
                        spacing=11,
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
            self._memory,
            self._settings,
        ]
        return builders[index]()

    def _nav(self) -> ft.NavigationRail:
        rail = super()._nav()
        rail.destinations.insert(
            7,
            ft.NavigationRailDestination(
                icon=ft.Icons.MEMORY,
                label="Memory",
            ),
        )
        return rail

    async def _log_pump(self) -> None:
        while self.page is not None:
            if self._selected_index == 4:
                await self._music_refresh()
            elif self._selected_index == 6:
                now = asyncio.get_running_loop().time()
                if now - self._schedule_last_refresh >= 2.0:
                    self._schedule_last_refresh = now
                    await self._refresh_schedule()
            elif self._selected_index == 8:
                await self._refresh_logs()
            await asyncio.sleep(0.6)
