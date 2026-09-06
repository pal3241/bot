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
        self._last_runtime_signature: tuple[object, ...] | None = None
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
        self._bind_runtime_events()
        self._log_loaded(catalog)
        print(
            "[SENNA EXPRESSION] internet GIF search="
            + (
                "ENABLED provider=tenor"
                if self.gif_search.enabled
                else "DISABLED (TENOR_API_KEY missing or disabled)"
            )
        )

    def _bind_runtime_events(self) -> None:
        async def on_guild_emojis_update(
            guild: discord.Guild,
            before: tuple[discord.Emoji, ...],
            after: tuple[discord.Emoji, ...],
        ) -> None:
            del guild, before, after
            try:
                self.refresh_runtime(force=True)
            except Exception as error:
                print(
                    f"[SENNA EXPRESSION] emoji hot-sync failed "
                    f"type={type(error).__name__} detail={error}"
                )

        async def on_guild_stickers_update(
            guild: discord.Guild,
            before: tuple[discord.GuildSticker, ...],
            after: tuple[discord.GuildSticker, ...],
        ) -> None:
            del guild, before, after
            try:
                self.refresh_runtime(force=True)
            except Exception as error:
                print(
                    f"[SENNA EXPRESSION] sticker hot-sync failed "
                    f"type={type(error).__name__} detail={error}"
                )

        self._client.event(on_guild_emojis_update)
        self._client.event(on_guild_stickers_update)

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

    def _runtime_signature(self) -> tuple[object, ...]:
        emoji_signature = tuple(
            sorted(
                (
                    int(emoji.id),
                    str(emoji.name),
                    int(emoji.guild_id),
                    bool(emoji.animated),
                )
                for emoji in self._client.emojis
            )
        )
        sticker_signature: list[tuple[object, ...]] = []
        for guild in self._client.guilds:
            for sticker in getattr(guild, "stickers", ()):
                sticker_signature.append(
                    (
                        int(sticker.id),
                        str(sticker.name),
                        int(sticker.guild_id),
                    )
                )
        return (emoji_signature, tuple(sorted(sticker_signature)))

    def refresh_runtime(self, *, force: bool = False) -> bool:
        # Health polling asks for status every few seconds. Once runtime assets
        # have been synced, that polling must not rebuild the catalog or refresh
        # the sender cache. Discord gateway events/manual sync use force=True.
        if self._last_runtime_signature is not None and not force:
            return False

        signature = self._runtime_signature()
        runtime_catalog, stats = auto_sync_catalog(self._base_catalog, self._client)
        self._sync_stats = stats
        self._resolver.replace_catalog(runtime_catalog)
        self.sender.refresh_runtime_emojis()
        self._last_runtime_signature = signature
        print(
            f"[SENNA EXPRESSION] auto-sync emoji+={stats.emojis_added} "
            f"sticker+={stats.stickers_added} totals="
            f"{stats.total_emojis}/{stats.total_stickers}"
        )
        return True

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
        self._last_runtime_signature = None
        self.refresh_runtime(force=True)
        self._log_loaded(self._resolver.catalog)
        return True
