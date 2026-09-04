from __future__ import annotations

from dataclasses import replace
from typing import Any

import flet as ft

from ui.flet_app import ERROR, MUTED, SUCCESS, TEXT
from ui.flet_app_music_runtime import SenaFletUI as _BaseSenaFletUI


class SenaFletUI(_BaseSenaFletUI):
    """Expose network-oriented stream quality presets for Music."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        manager = self.ctx.music
        profile = manager.settings.stream_profile if manager is not None else "low"
        self.music_stream_profile = ft.Dropdown(
            label="Streaming profile",
            value=profile,
            options=self._options(
                [
                    ("low", "Low bandwidth · prefer ≤96 kbps"),
                    ("balanced", "Balanced · prefer ≤128 kbps"),
                    ("high", "High quality · best audio"),
                ]
            ),
            expand=True,
        )
        self.music_bandwidth_status = ft.Text("", color=MUTED, size=11)

    async def _music_save_bandwidth(self, e: Any = None) -> None:
        del e
        try:
            manager = self._music_manager()
            profile = str(self.music_stream_profile.value or "low").strip().casefold()
            saved = await manager.apply_settings(
                replace(manager.settings, stream_profile=profile)
            )
            self.music_stream_profile.value = saved.stream_profile
            labels = {
                "low": "Low bandwidth aktif · target audio ≤96 kbps bila tersedia.",
                "balanced": "Balanced aktif · target audio ≤128 kbps bila tersedia.",
                "high": "High quality aktif · yt-dlp memilih best audio.",
            }
            self.music_bandwidth_status.value = (
                labels.get(saved.stream_profile, f"Profile aktif: {saved.stream_profile}")
                + " Berlaku mulai track berikutnya."
            )
            self.music_bandwidth_status.color = SUCCESS
        except Exception as error:
            self.music_bandwidth_status.value = (
                f"Bandwidth setting gagal · {type(error).__name__}: {error}"
            )
            self.music_bandwidth_status.color = ERROR
        if self.page:
            self.page.update()

    def _music(self) -> ft.Control:
        body = super()._music()
        manager = self.ctx.music
        if manager is not None:
            self.music_stream_profile.value = manager.settings.stream_profile

        bandwidth_panel = self._panel(
            ft.Column(
                controls=[
                    ft.Text(
                        "Network / bandwidth",
                        color=TEXT,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        "Low bandwidth hanya meminta stream audio ringan dari sumber. "
                        "Video tetap tidak diputar. Jika platform tidak punya audio di bawah "
                        "target, yt-dlp akan fallback ke audio berikutnya agar playback tetap jalan.",
                        color=MUTED,
                        size=10,
                    ),
                    self.music_stream_profile,
                    ft.Button(
                        "Apply streaming profile",
                        icon=ft.Icons.NETWORK_CHECK,
                        on_click=self._music_save_bandwidth,
                    ),
                    self.music_bandwidth_status,
                ],
                spacing=10,
            )
        )

        content = getattr(body, "content", None)
        controls = getattr(content, "controls", None)
        if isinstance(controls, list):
            controls.append(bandwidth_panel)
        return body
