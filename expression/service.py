import random
import time
from pathlib import Path

import discord

from expression.exceptions import ExpressionCatalogError
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
        self.sender = DiscordExpressionSender(client, self._resolver)
        self._log_loaded(catalog)

    @staticmethod
    def _log_loaded(catalog: ExpressionCatalog) -> None:
        print(
            f"[SENNA EXPRESSION] catalog loaded emojis={len(catalog.emojis)} "
            f"stickers={len(catalog.stickers)} gifs={len(catalog.gifs)}"
        )

    def refresh_runtime(self) -> None:
        self.sender.refresh_runtime_emojis()

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
        self._resolver.replace_catalog(catalog)
        self.sender.refresh_runtime_emojis()
        self._log_loaded(catalog)
        return True
