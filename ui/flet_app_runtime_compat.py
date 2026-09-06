from __future__ import annotations

from typing import Any

import flet as ft

from ui.flet_app import ERROR, SUCCESS
from ui.flet_app_expression import SenaFletUI as _BaseSenaFletUI


class SenaFletUI(_BaseSenaFletUI):
    """Runtime compatibility fixes for the current Flet dialog API."""

    async def _show_process_confirmation(self, *, restart: bool) -> None:
        if self.page is None:
            return

        action_label = "Restart Bot" if restart else "Matikan Bot"
        explanation = (
            "Senna akan menutup semua subsystem dengan rapi, lalu menjalankan ulang program."
            if restart
            else "Senna akan menutup semua subsystem dan keluar dari program."
        )

        async def cancel(e: Any) -> None:
            del e
            if self.page is not None:
                self.page.pop_dialog()
                self.page.update()

        async def confirm(e: Any) -> None:
            del e
            if self.page is not None:
                self.page.pop_dialog()
                self.page.update()
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
        self.page.show_dialog(dialog)
        self.page.update()

    async def _reset_all_sessions(self, e: Any) -> None:
        del e
        if self.page is None:
            return

        async def cancel(event: Any) -> None:
            del event
            if self.page is not None:
                self.page.pop_dialog()
                self.page.update()

        async def confirm(event: Any) -> None:
            del event
            removed = (
                self.ctx.assistant.sessions.clear()
                if self.ctx.assistant is not None
                else 0
            )
            self.settings_status.value = (
                f"Semua session direset ({removed} session). "
                "Memory dan konfigurasi tidak dihapus."
            )
            self.settings_status.color = SUCCESS
            if self.page is not None:
                self.page.pop_dialog()
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
        self.page.show_dialog(dialog)
        self.page.update()

    async def _expression_sync_now(self, e: Any = None) -> None:
        del e
        try:
            service = self._expression_service()
            changed = service.refresh_runtime(force=True)
            self.expression_test_result.value = (
                "Discord emoji/sticker runtime berhasil di-sync ulang."
                if changed
                else "Runtime asset sudah sama; tidak ada perubahan."
            )
            self.expression_test_result.color = SUCCESS
        except Exception as error:
            self.expression_test_result.value = (
                f"Sync gagal · {type(error).__name__}: {error}"
            )
            self.expression_test_result.color = ERROR
        await self._expression_refresh()
