from __future__ import annotations

import asyncio
from typing import Any

import flet as ft

from ui.flet_app import BORDER, ERROR, MUTED, SUCCESS, TEXT, WARNING
from ui.flet_app_memory import SenaFletUI as _BaseSenaFletUI


class SenaFletUI(_BaseSenaFletUI):
    """Expression runtime control center for Discord auto-sync and internet GIFs."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.expression_status = ft.Text("Belum dimuat.", color=MUTED, size=11)
        self.expression_counts = ft.Text(
            "Emoji 0 · Sticker 0 · Local GIF 0",
            color=MUTED,
            size=11,
        )
        self.expression_assets = ft.Text(
            "Belum dimuat.",
            color="#D8D8D8",
            size=11,
            selectable=True,
        )
        self.expression_test_query = ft.TextField(
            label="Test internet GIF query",
            hint_text="contoh: excited celebration reaction",
            border_color=BORDER,
        )
        self.expression_test_result = ft.Text("", color=MUTED, size=11, selectable=True)
        self._expression_last_refresh = 0.0

    def _expression_service(self):
        service = getattr(self.ctx, "expression_service", None)
        if service is None:
            raise RuntimeError("Expression service tidak aktif.")
        return service

    async def _expression_refresh(self, e: Any = None) -> None:
        del e
        try:
            service = self._expression_service()
            catalog = service.catalog
            stats = service.sync_stats
            auto_emoji = sum(1 for item in catalog.emojis if item.key.startswith("auto:emoji:"))
            auto_sticker = sum(1 for item in catalog.stickers if item.key.startswith("auto:sticker:"))
            manual_emoji = len(catalog.emojis) - auto_emoji
            manual_sticker = len(catalog.stickers) - auto_sticker
            gif_enabled = bool(service.gif_search.enabled)

            self.expression_status.value = (
                "Expression ONLINE · "
                + ("Internet GIF READY" if gif_enabled else "Internet GIF OFF")
            )
            self.expression_status.color = SUCCESS if gif_enabled else WARNING
            self.expression_counts.value = (
                f"Emoji {len(catalog.emojis)} (auto {auto_emoji}, manual {manual_emoji}) · "
                f"Sticker {len(catalog.stickers)} (auto {auto_sticker}, manual {manual_sticker}) · "
                f"Local GIF {len(catalog.gifs)}"
            )

            lines: list[str] = [
                f"Auto-sync last refresh · emoji+={stats.emojis_added} sticker+={stats.stickers_added}",
                f"Internet provider · {'Tenor enabled' if gif_enabled else 'disabled; isi TENOR_API_KEY'}",
                "",
                "Emoji runtime:",
            ]
            for item in catalog.emojis[:40]:
                source = "AUTO" if item.key.startswith("auto:") else "MANUAL"
                lines.append(
                    f"[{source}] {item.name} · emotion={item.emotion.value} · "
                    f"guild={item.guild_id or '-'} · id={item.discord_id or '-'}"
                )
            if len(catalog.emojis) > 40:
                lines.append(f"... +{len(catalog.emojis) - 40} emoji lain")

            lines.extend(("", "Sticker runtime:"))
            for item in catalog.stickers[:30]:
                source = "AUTO" if item.key.startswith("auto:") else "MANUAL"
                lines.append(
                    f"[{source}] {item.name} · emotion={item.emotion.value} · "
                    f"guild={item.guild_id or '-'} · id={item.discord_id or '-'}"
                )
            if len(catalog.stickers) > 30:
                lines.append(f"... +{len(catalog.stickers) - 30} sticker lain")
            self.expression_assets.value = "\n".join(lines)
        except Exception as error:
            self.expression_status.value = (
                f"Expression refresh gagal · {type(error).__name__}: {error}"
            )
            self.expression_status.color = ERROR
        if self.page:
            self.page.update()

    async def _expression_sync_now(self, e: Any = None) -> None:
        del e
        try:
            service = self._expression_service()
            service.refresh_runtime()
            self.expression_test_result.value = "Discord emoji/sticker runtime berhasil di-sync ulang."
            self.expression_test_result.color = SUCCESS
        except Exception as error:
            self.expression_test_result.value = (
                f"Sync gagal · {type(error).__name__}: {error}"
            )
            self.expression_test_result.color = ERROR
        await self._expression_refresh()

    async def _expression_test_gif(self, e: Any = None) -> None:
        del e
        try:
            service = self._expression_service()
            query = " ".join((self.expression_test_query.value or "").split()).strip()
            if not query:
                raise ValueError("Isi query test GIF terlebih dahulu.")
            if not service.gif_search.enabled:
                raise RuntimeError("Tenor belum aktif. Isi TENOR_API_KEY di .env lalu restart Sena.")
            result = await service.gif_search.search_query(query)
            if result is None:
                self.expression_test_result.value = "Tenor tidak mengembalikan GIF yang dapat dipakai."
                self.expression_test_result.color = WARNING
            else:
                self.expression_test_result.value = (
                    f"Tenor OK · id={result.content_id}\n"
                    f"query={result.query}\n"
                    f"{result.media_url}"
                )
                self.expression_test_result.color = SUCCESS
        except Exception as error:
            self.expression_test_result.value = (
                f"GIF test gagal · {type(error).__name__}: {error}"
            )
            self.expression_test_result.color = ERROR
        if self.page:
            self.page.update()

    def _expression(self) -> ft.Control:
        if self.page:
            self.page.run_task(self._expression_refresh)
        return self._body(
            [
                self._title(
                    "Expression",
                    "Auto-sync Discord emoji/sticker dan privacy-safe internet GIF fallback",
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        "Runtime assets",
                                        color=TEXT,
                                        weight=ft.FontWeight.W_600,
                                        expand=True,
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.REFRESH,
                                        on_click=self._expression_refresh,
                                    ),
                                ]
                            ),
                            self.expression_status,
                            self.expression_counts,
                            ft.Text(
                                "Manual expressions.json tetap punya prioritas. Asset Discord yang ditemukan otomatis hanya menjadi runtime overlay dan tidak menulis ulang config.",
                                color=MUTED,
                                size=10,
                            ),
                            ft.Button(
                                "Sync Discord Assets Now",
                                icon=ft.Icons.SYNC,
                                on_click=self._expression_sync_now,
                            ),
                        ],
                        spacing=9,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("Internet GIF", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.Text(
                                "Sena mencari GIF melalui Tenor hanya saat Expression meminta GIF, intensity/cooldown lolos, dan tidak ada local GIF catalog. Query otomatis berasal dari emotion + intent; teks chat mentah tidak dikirim ke Tenor.",
                                color=MUTED,
                                size=10,
                            ),
                            self.expression_test_query,
                            ft.Button(
                                "Test Tenor Search",
                                icon=ft.Icons.SEARCH,
                                on_click=self._expression_test_gif,
                            ),
                            self.expression_test_result,
                        ],
                        spacing=10,
                    )
                ),
                self._panel(
                    ft.Column(
                        controls=[
                            ft.Text("Catalog Preview", color=TEXT, weight=ft.FontWeight.W_600),
                            ft.Container(
                                height=360 if self._compact else 500,
                                padding=12,
                                bgcolor="#080808",
                                border=ft.Border.all(1, BORDER),
                                border_radius=12,
                                content=ft.Column(
                                    controls=[self.expression_assets],
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
            self._music,
            self._ai_settings,
            self._schedule,
            self._memory,
            self._expression,
            self._settings,
        ]
        return builders[index]()

    def _nav(self) -> ft.NavigationRail:
        rail = super()._nav()
        rail.destinations.insert(
            8,
            ft.NavigationRailDestination(
                icon=ft.Icons.AUTO_AWESOME,
                label="Expression",
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
                now = asyncio.get_running_loop().time()
                if now - self._expression_last_refresh >= 5.0:
                    self._expression_last_refresh = now
                    await self._expression_refresh()
            elif self._selected_index == 9:
                await self._refresh_logs()
            await asyncio.sleep(0.6)
