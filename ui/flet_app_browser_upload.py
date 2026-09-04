from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import discord
import flet as ft

from config import MAX_EMOJI_SIZE
from ui.flet_app import (
    ERROR,
    MUTED,
    SUCCESS,
    TEXT,
    WARNING,
    SenaFletUI as _BaseSenaFletUI,
)


_ALLOWED_EMOJI_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


class SenaFletUI(_BaseSenaFletUI):
    """Control center with direct browser -> Discord multi-file emoji uploads."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._browser_emoji_files: list[ft.FilePickerFile] = []
        self.emoji_file_picker = ft.FilePicker()
        self.emoji_browser_files = ft.Text(
            "Belum ada file dipilih.",
            size=11,
            color=MUTED,
            selectable=True,
        )
        self.emoji_browser_status = ft.Text("", size=11, color=MUTED)
        self.emoji_browser_upload_button = ft.Button(
            "Upload selected",
            icon=ft.Icons.CLOUD_UPLOAD_OUTLINED,
            on_click=self._emoji_browser_upload_selected,
            disabled=True,
        )

    async def main(self, page: ft.Page) -> None:
        # Build the normal page first so the Flet web session/control tree is alive,
        # then register FilePicker as a service and force one synchronization. This is
        # required by the 0.86 service API before _invoke_method()/pick_files() works.
        await super().main(page)
        if self.emoji_file_picker not in page.services:
            page.services.append(self.emoji_file_picker)
        page.update()
        await asyncio.sleep(0)
        print("[SENA UI EMOJI] FilePicker service mounted")

    async def _ensure_file_picker_mounted(self) -> None:
        page = self.page
        if page is None:
            raise RuntimeError("Flet page belum siap.")

        try:
            _ = self.emoji_file_picker.page
            return
        except RuntimeError:
            pass

        if self.emoji_file_picker not in page.services:
            page.services.append(self.emoji_file_picker)
        page.update()
        await asyncio.sleep(0)

        try:
            _ = self.emoji_file_picker.page
        except RuntimeError as error:
            raise RuntimeError(
                "FilePicker service belum mounted ke Flet page setelah sync."
            ) from error

    def _format_browser_selection(self) -> str:
        if not self._browser_emoji_files:
            return "Belum ada file dipilih."
        lines: list[str] = []
        total_size = 0
        for file in self._browser_emoji_files:
            size = int(file.size or 0)
            total_size += size
            marker = "OK" if size <= MAX_EMOJI_SIZE else "TERLALU BESAR"
            lines.append(f"• {file.name} · {size / 1024:.1f} KB · {marker}")
        lines.append(
            f"\n{len(self._browser_emoji_files)} file · total {total_size / 1024:.1f} KB"
        )
        return "\n".join(lines)

    def _set_browser_selection(self, files: list[ft.FilePickerFile]) -> None:
        self._browser_emoji_files = files
        self.emoji_browser_files.value = self._format_browser_selection()
        self.emoji_browser_upload_button.disabled = not bool(files)
        if not files:
            self.emoji_browser_status.value = "Pemilihan dibatalkan."
            self.emoji_browser_status.color = MUTED
            return

        too_large = sum(
            1 for file in files if int(file.size or 0) > MAX_EMOJI_SIZE
        )
        self.emoji_browser_status.value = (
            f"Dipilih {len(files)} file"
            + (
                f" · {too_large} akan dilewati karena > "
                f"{MAX_EMOJI_SIZE / 1024:.0f} KB"
                if too_large
                else ""
            )
        )
        self.emoji_browser_status.color = WARNING if too_large else SUCCESS

    async def _emoji_browser_pick_files(self, e: Any) -> None:
        del e
        try:
            await self._ensure_file_picker_mounted()
            files = await self.emoji_file_picker.pick_files(
                allow_multiple=True,
                with_data=True,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=sorted(_ALLOWED_EMOJI_EXTENSIONS),
            )
            self._set_browser_selection(list(files or []))
        except Exception as error:
            self._browser_emoji_files.clear()
            self.emoji_browser_files.value = "Belum ada file dipilih."
            self.emoji_browser_upload_button.disabled = True
            self.emoji_browser_status.value = (
                f"File picker gagal · {type(error).__name__}: {error}"
            )
            self.emoji_browser_status.color = ERROR
            print(
                f"[SENA UI EMOJI] file picker failed "
                f"type={type(error).__name__} detail={error}"
            )
        if self.page:
            self.page.update()

    def _emoji_name_from_browser_file(
        self,
        file_name: str,
        existing: set[str],
        requested_name: str = "",
    ) -> str:
        return self._emoji_name_for_path(
            Path(file_name),
            existing,
            requested_name=requested_name,
        )

    async def _emoji_browser_upload_selected(self, e: Any) -> None:
        del e
        guild = self._emoji_selected_guild()
        if guild is None:
            self.emoji_browser_status.value = "Pilih server dulu."
            self.emoji_browser_status.color = ERROR
            if self.page:
                self.page.update()
            return
        if not self._browser_emoji_files:
            self.emoji_browser_status.value = "Pilih minimal satu file."
            self.emoji_browser_status.color = ERROR
            if self.page:
                self.page.update()
            return

        existing = {emoji.name for emoji in guild.emojis}
        success = 0
        skipped = 0
        failed = 0
        total = len(self._browser_emoji_files)
        self.emoji_browser_upload_button.disabled = True

        try:
            for index, file in enumerate(self._browser_emoji_files, start=1):
                suffix = Path(file.name).suffix.casefold().lstrip(".")
                size = int(file.size or 0)
                if suffix not in _ALLOWED_EMOJI_EXTENSIONS or size > MAX_EMOJI_SIZE:
                    skipped += 1
                    continue

                data = file.bytes
                if data is None:
                    failed += 1
                    print(
                        f"[SENA UI EMOJI] browser bytes missing file={file.name}; "
                        "pick_files must use with_data=True"
                    )
                    continue

                requested_name = (
                    (self.emoji_name.value or "").strip() if total == 1 else ""
                )
                emoji_name = self._emoji_name_from_browser_file(
                    file.name,
                    existing,
                    requested_name,
                )
                self.emoji_browser_status.value = (
                    f"Uploading {index}/{total} · {file.name} → {emoji_name}"
                )
                self.emoji_browser_status.color = MUTED
                if self.page:
                    self.page.update()

                try:
                    emoji = await guild.create_custom_emoji(
                        name=emoji_name,
                        image=bytes(data),
                        reason="Senna browser multi-file emoji uploader",
                    )
                except discord.Forbidden:
                    self.emoji_browser_status.value = (
                        "Bot tidak punya permission Manage Expressions/Emoji."
                    )
                    self.emoji_browser_status.color = ERROR
                    return
                except discord.HTTPException as error:
                    failed += 1
                    print(
                        f"[SENA UI EMOJI] upload failed file={file.name} "
                        f"status={error.status} detail={error.text}"
                    )
                    continue

                existing.add(emoji.name)
                success += 1
        finally:
            self.emoji_browser_upload_button.disabled = False

        self.emoji_browser_status.value = (
            f"Selesai · berhasil={success} · skip={skipped} · gagal={failed}"
        )
        self.emoji_browser_status.color = SUCCESS if success else WARNING
        self._browser_emoji_files.clear()
        self.emoji_browser_files.value = "Belum ada file dipilih."
        self.emoji_browser_upload_button.disabled = True
        self._refresh_emoji_list()
        if self.page:
            self.page.update()

    def _browser_upload_panel(self) -> ft.Control:
        return self._panel(
            ft.Column(
                controls=[
                    ft.Button(
                        content=ft.Container(
                            height=150 if self._compact else 180,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Column(
                                controls=[
                                    ft.Icon(
                                        ft.Icons.CLOUD_UPLOAD_OUTLINED,
                                        size=38,
                                        color="#BDBDBD",
                                    ),
                                    ft.Text(
                                        "Pilih banyak emoji dari laptop",
                                        color=TEXT,
                                        weight=ft.FontWeight.W_600,
                                        size=15,
                                    ),
                                    ft.Text(
                                        "PNG · JPG · GIF · WEBP  |  multi-select aktif",
                                        color=MUTED,
                                        size=10,
                                    ),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=7,
                            ),
                        ),
                        on_click=self._emoji_browser_pick_files,
                        expand=True,
                    ),
                    ft.Text(
                        "File dibaca langsung oleh browser dan dikirim ke Discord; "
                        "tidak perlu SFTP atau path Termux.",
                        color=MUTED,
                        size=10,
                    ),
                    self.emoji_browser_files,
                    ft.Row(
                        wrap=True,
                        controls=[
                            self.emoji_browser_upload_button,
                            self.emoji_browser_status,
                        ],
                    ),
                ],
                spacing=12,
            )
        )

    def _emoji(self) -> ft.Control:
        # Reuse the full base Emoji manager (server selection, local-path fallback,
        # delete manager, inventory) and insert browser multi-select as the primary
        # panel. This avoids duplicating the whole page and keeps future base fixes.
        view = super()._emoji()
        body = getattr(view, "content", None)
        controls = getattr(body, "controls", None)
        if isinstance(controls, list):
            insert_at = 2 if len(controls) >= 2 else len(controls)
            controls.insert(insert_at, self._browser_upload_panel())
        return view
