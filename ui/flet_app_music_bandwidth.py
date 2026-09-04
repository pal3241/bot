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
                    ("data_saver", "Data Saver · source ≤48 kbps · Discord 48 kbps"),
                    ("ultra_low", "Ultra Low · source ≤64 kbps · Discord 64 kbps"),
                    ("low", "Low · source ≤96 kbps · Discord 80 kbps"),
                    ("balanced", "Balanced · source ≤128 kbps · Discord 96 kbps"),
                    ("high", "High quality · best audio · Discord 128 kbps"),
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
                "data_saver": (
                    "Data Saver aktif · sumber target ≤48 kbps + Discord Opus 48 kbps."
                ),
                "ultra_low": (
                    "Ultra Low aktif · sumber target ≤64 kbps + Discord Opus 64 kbps."
                ),
                "low": "Low aktif · sumber target ≤96 kbps + Discord Opus 80 kbps.",
                "balanced": (
                    "Balanced aktif · sumber target ≤128 kbps + Discord Opus 96 kbps."
                ),
                "high": "High quality aktif · best audio + Discord Opus 128 kbps.",
            }
            self.music_bandwidth_status.value = (
                labels.get(saved.stream_profile, f"Profile aktif: {saved.stream_profile}")
                + " Berlaku mulai track berikutnya."
            )
            self.music_bandwidth_status.color = SUCCESS
            self.music_backend.value = manager.backend_status()
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
                        "Profile sekarang menghemat dua arah: stream audio sumber → device "
                        "dan encoder Opus device → Discord. Video tetap tidak diputar. "
                        "Jika platform tidak menyediakan bitrate serendah target, yt-dlp "
                        "akan fallback ke audio berikutnya agar playback tetap jalan.",
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
