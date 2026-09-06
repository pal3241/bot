import random
import time
from pathlib import Path

import discord

from expression.autosync import AutoSyncStats, auto_sync_catalog
from expression.exceptions import ExpressionCatalogError
from expression.gif_search import TenorGifSearch
from expression.history import ExpressionHistory
from expression.loader import empty_catalog, load_catalog
from expression.models import ExpressionCatalog
from expression.resolver import ExpressionResolver
from expression.sender import DiscordExpressionSender


class ExpressionService:
    def __init__(
        self,
        client: discord.Client,
        catalog_path: Path,
        asset_root: Path,
    ) -> None:
        self._client: discord.Client = client
        self._catalog_path: Path = catalog_path
        self._asset_root: Path = asset_root
        try:
            catalog: ExpressionCatalog = load_catalog(catalog_path, asset_root)
        except ExpressionCatalogError as error:
            catalog = empty_catalog()
            print(
                f"[SENNA EXPRESSION] startup catalog invalid detail={error}; "
                "using Unicode fallback"
            )
        self._base_catalog = catalog
        self._sync_stats = AutoSyncStats(0, 0, len(catalog.emojis), len(catalog.stickers))
        self.gif_search = TenorGifSearch.from_env()
        history = ExpressionHistory(
            catalog.policy.recent_emoji_size,
            catalog.policy.recent_bonus_size,
            3600.0,
        )
        self._resolver = ExpressionResolver(
            catalog,
            history,
            random.Random(),
            time.monotonic,
        )
        self.sender = DiscordExpressionSender(
            client,
            self._resolver,
            gif_search=self.gif_search,
        )
        self._log_loaded(catalog)
        print(
            "[SENNA EXPRESSION] internet GIF search="
            + ("ENABLED provider=tenor" if self.gif_search.enabled else "DISABLED (TENOR_API_KEY missing or disabled)")
        )

    @staticmethod
    def _log_loaded(catalog: ExpressionCatalog) -> None:
        print(
            f"[SENNA EXPRESSION] catalog loaded emojis={len(catalog.emojis)} "
            f"stickers={len(catalog.stickers)} gifs={len(catalog.gifs)}"
        )

    @property
    def sync_stats(self) -> AutoSyncStats:
        return self._sync_stats

    @property
    def catalog(self) -> ExpressionCatalog:
        return self._resolver.catalog

    def status_detail(self) -> str:
        stats = self._sync_stats
        gif_state = "tenor:on" if self.gif_search.enabled else "tenor:off"
        return (
            f"emoji={stats.total_emojis} sticker={stats.total_stickers} "
            f"local_gif={len(self._resolver.catalog.gifs)} {gif_state}"
        )

    def refresh_runtime(self) -> None:
        runtime_catalog, stats = auto_sync_catalog(self._base_catalog, self._client)
        self._sync_stats = stats
        self._resolver.replace_catalog(runtime_catalog)
        self.sender.refresh_runtime_emojis()
        print(
            f"[SENNA EXPRESSION] auto-sync emoji+={stats.emojis_added} "
            f"sticker+={stats.stickers_added} totals="
            f"{stats.total_emojis}/{stats.total_stickers}"
        )

    def reload(self) -> bool:
        try:
            catalog: ExpressionCatalog = load_catalog(
                self._catalog_path, self._asset_root
            )
        except ExpressionCatalogError as error:
            print(
                f"[SENNA EXPRESSION] catalog reload rejected detail={error}; "
                "previous catalog retained"
            )
            return False
        self._base_catalog = catalog
        self.refresh_runtime()
        self._log_loaded(self._resolver.catalog)
        return True
