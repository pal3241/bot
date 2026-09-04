from __future__ import annotations

from typing import Any

import flet as ft

from core.feature_loader import feature_health_summary
from core.runtime_log import RUNTIME_LOGS
from ui.flet_app import (
    MUTED,
    TEXT,
    WEB_PORT,
    SenaFletUI as _BaseSenaFletUI,
)


class SenaFletUI(_BaseSenaFletUI):
    """Flet UI with a log-first Settings layout and startup log history."""

    def _log_text(self) -> str:
        lines = RUNTIME_LOGS.snapshot()
        if lines:
            return "\n".join(lines)
        return (
            "[SENA UI] Belum ada runtime log.\n"
            "Log startup, feature loader, AI, action, warning, dan error akan "
            "muncul otomatis di sini."
        )

    async def _refresh_logs(self, e: Any = None) -> None:
        del e
        self.log_view.value = self._log_text()
        if self.page:
            self.page.update()

    async def _clear_logs(self, e: Any) -> None:
        del e
        RUNTIME_LOGS.clear()
        with self._log_lock:
            self._logs.clear()
        self.log_view.value = self._log_text()
        if self.page:
            self.page.update()

    def _settings(self) -> ft.Control:
        self.log_view.value = self._log_text()
        web_info = (
            f"0.0.0.0:{WEB_PORT} · local http://127.0.0.1:{WEB_PORT}"
            if self.device.is_android
            else "Desktop Flet app"
        )

        log_header = self._panel(
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=8,
                controls=[
                    ft.Column(
                        spacing=1,
                        expand=True,
                        controls=[
                            ft.Text(
                                "Live runtime logs",
                                color=TEXT,
                                size=14,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                "Startup + runtime · auto-refresh 0.8 detik",
                                color=MUTED,
                                size=10,
                            ),
                        ],
                    ),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH,
                        tooltip="Refresh logs",
                        on_click=self._refresh_logs,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        tooltip="Clear logs",
                        on_click=self._clear_logs,
                    ),
                ],
            )
        )

        log_panel = ft.Container(
            height=500 if self._compact else 600,
            content=self._panel(
                self.log_view,
                expand=True,
                padding=10,
            ),
        )

        runtime_cards = ft.ResponsiveRow(
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
                    feature_health_summary(self.feature_results)
                    .replace("features=", "")
                    .replace(" enabled", ""),
                    ft.Icons.EXTENSION_OUTLINED,
                    detail="enabled / total",
                ),
                self._stat_card(
                    "Web UI",
                    str(WEB_PORT) if self.device.is_android else "desktop",
                    ft.Icons.LANGUAGE_OUTLINED,
                    detail=(
                        "LAN enabled"
                        if self.device.is_android
                        else "native window"
                    ),
                ),
            ],
        )

        endpoint_panel = self._panel(
            ft.Column(
                spacing=7,
                controls=[
                    ft.Text(
                        "Runtime endpoint",
                        color=TEXT,
                        size=14,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(web_info, color=MUTED, size=11),
                    ft.Text(
                        self.runtime_status.summary(),
                        color=MUTED,
                        size=11,
                    ),
                ],
            )
        )

        return self._page_body(
            [
                self._title("Settings", "Runtime, network dan live logs"),
                log_header,
                log_panel,
                runtime_cards,
                endpoint_panel,
            ]
        )
