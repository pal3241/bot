from __future__ import annotations

import os
from typing import Any

import flet as ft

from config import MAX_EMOJI_SIZE
from ui.emoji_upload_server import EmojiUploadServer
from ui.flet_app import (
    BORDER,
    MUTED,
    SUCCESS,
    TEXT,
    WARNING,
    WEB_HOST,
    SenaFletUI as _BaseSenaFletUI,
)


EMOJI_UPLOAD_PORT = int(os.getenv("SENA_EMOJI_UPLOAD_PORT", "8551"))


class SenaFletUI(_BaseSenaFletUI):
    """Senna control center with a native HTML drag/drop emoji uploader."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.emoji_upload_server = EmojiUploadServer(
            self.ctx.client,
            host=WEB_HOST,
            port=EMOJI_UPLOAD_PORT,
            max_emoji_size=MAX_EMOJI_SIZE,
        )
        self.emoji_web_status = ft.Text("Uploader belum aktif.", color=MUTED, size=11)

    def _browser_upload_panel(self) -> ft.Control:
        if self.emoji_upload_server.running:
            url = self.emoji_upload_server.public_url
            status = "ONLINE"
            status_color = SUCCESS
        else:
            url = f"http://<PHONE-LAN-IP>:{EMOJI_UPLOAD_PORT}/"
            status = "OFFLINE"
            status_color = WARNING

        return self._panel(
            ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text(
                                        "Browser drag & drop uploader",
                                        color=TEXT,
                                        weight=ft.FontWeight.W_600,
                                        size=15,
                                    ),
                                    ft.Text(
                                        "Multi-file upload langsung dari laptop ke Discord tanpa FilePicker Flet atau SFTP.",
                                        color=MUTED,
                                        size=10,
                                    ),
                                ],
                                spacing=3,
                                expand=True,
                            ),
                            ft.Container(
                                padding=ft.Padding.symmetric(horizontal=9, vertical=5),
                                border=ft.Border.all(1, BORDER),
                                border_radius=16,
                                content=ft.Text(status, color=status_color, size=9),
                            ),
                        ]
                    ),
                    ft.Text(
                        "Buka URL ini di browser laptop, lalu drag & drop PNG/JPG/GIF/WEBP. Kamu juga bisa klik drop zone dan pilih banyak file sekaligus.",
                        color=MUTED,
                        size=11,
                    ),
                    ft.Container(
                        padding=12,
                        bgcolor="#080808",
                        border=ft.Border.all(1, BORDER),
                        border_radius=12,
                        content=ft.Text(
                            url,
                            color="#D8D8D8",
                            size=12,
                            selectable=True,
                        ),
                    ),
                    ft.Text(
                        f"Port uploader: {EMOJI_UPLOAD_PORT} · maksimum {MAX_EMOJI_SIZE / 1024:.0f} KB per emoji · URL memakai token sesi acak.",
                        color=MUTED,
                        size=10,
                    ),
                    self.emoji_web_status,
                ],
                spacing=12,
            )
        )

    def _emoji(self) -> ft.Control:
        view = super()._emoji()
        body = getattr(view, "content", None)
        controls = getattr(body, "controls", None)
        if isinstance(controls, list):
            # Put native browser upload first, immediately after the page title.
            insert_at = 1 if controls else 0
            controls.insert(insert_at, self._browser_upload_panel())
        return view

    async def run(self) -> None:
        uploader_started = False
        try:
            await self.emoji_upload_server.start()
            uploader_started = True
            self.emoji_web_status.value = "Drag & drop uploader siap."
            self.emoji_web_status.color = SUCCESS
            print(
                f"[SENA UI EMOJI] Native upload server ready "
                f"url={self.emoji_upload_server.public_url}"
            )
        except Exception as error:
            self.emoji_web_status.value = (
                f"Uploader gagal start · {type(error).__name__}: {error}"
            )
            self.emoji_web_status.color = WARNING
            print(
                f"[SENA UI EMOJI] Native upload server failed "
                f"type={type(error).__name__} detail={error}"
            )

        try:
            await super().run()
        finally:
            if uploader_started:
                await self.emoji_upload_server.stop()
                print("[SENA UI EMOJI] Native upload server stopped")
