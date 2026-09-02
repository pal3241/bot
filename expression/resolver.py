import random
from collections.abc import Callable

from expression.enums import AssetType, BonusMedia, ExpressionIntent
from expression.fallback import unicode_fallback
from expression.history import ConversationUsage, ExpressionHistory
from expression.models import (
    ExpressionAsset,
    ExpressionCatalog,
    ExpressionContext,
    ExpressionRequest,
    PrimaryExpression,
    RuntimeEmoji,
)
from expression.scoring import score_asset


Clock = Callable[[], float]


class ExpressionResolver:
    def __init__(
        self,
        catalog: ExpressionCatalog,
        history: ExpressionHistory,
        rng: random.Random,
        clock: Clock,
    ) -> None:
        self.catalog: ExpressionCatalog = catalog
        self.history: ExpressionHistory = history
        self._rng: random.Random = rng
        self._clock: Clock = clock
        self._runtime_emojis: dict[int, RuntimeEmoji] = {}
        self._failure_counts: dict[str, int] = {}
        self._disabled_until: dict[str, float] = {}

    def replace_catalog(self, catalog: ExpressionCatalog) -> None:
        self.catalog = catalog
        active_keys: set[str] = {
            asset.key
            for asset in (*catalog.emojis, *catalog.stickers, *catalog.gifs)
        }
        self._failure_counts = {
            key: count
            for key, count in self._failure_counts.items()
            if key in active_keys
        }
        self._disabled_until = {
            key: deadline
            for key, deadline in self._disabled_until.items()
            if key in active_keys
        }

    def replace_runtime_emojis(self, emojis: list[RuntimeEmoji]) -> None:
        self._runtime_emojis = {
            emoji.discord_id: emoji for emoji in emojis if emoji.available
        }
        available_keys: set[str] = {
            asset.key
            for asset in self.catalog.emojis
            if asset.discord_id in self._runtime_emojis
        }
        for key in available_keys:
            self._failure_counts.pop(key, None)
            self._disabled_until.pop(key, None)

    def _is_available(self, asset: ExpressionAsset, now: float) -> bool:
        disabled_until: float | None = self._disabled_until.get(asset.key)
        if disabled_until is not None and now < disabled_until:
            return False
        if asset.type is AssetType.EMOJI:
            return asset.discord_id is not None and asset.discord_id in self._runtime_emojis
        if asset.type is AssetType.GIF:
            return asset.local_path is not None
        return asset.discord_id is not None

    def _rank(
        self,
        assets: tuple[ExpressionAsset, ...],
        request: ExpressionRequest,
        context: ExpressionContext,
        recent: list[str],
        now: float,
    ) -> list[tuple[float, ExpressionAsset]]:
        ranked: list[tuple[float, ExpressionAsset]] = []
        for asset in assets:
            if not self._is_available(asset, now):
                continue
            score: float = score_asset(asset, request, recent, context.is_owner)
            if asset.guild_id is not None and asset.guild_id == context.guild_id:
                score += 0.02
            ranked.append((score, asset))
        return sorted(ranked, key=lambda item: item[0], reverse=True)

    def _choose(
        self, ranked: list[tuple[float, ExpressionAsset]]
    ) -> ExpressionAsset | None:
        if not ranked:
            return None
        policy = self.catalog.policy
        qualified: list[tuple[float, ExpressionAsset]] = [
            item for item in ranked if item[0] >= policy.min_candidate_score
        ]
        if not qualified:
            return None
        best_score: float = qualified[0][0]
        top: list[tuple[float, ExpressionAsset]] = [
            item
            for item in qualified[: policy.top_k]
            if item[0] >= best_score - policy.top_k_score_window
        ]
        total: float = sum(score for score, _ in top)
        if total <= 0.0:
            return top[0][1]
        target: float = self._rng.random() * total
        cumulative: float = 0.0
        for score, asset in top:
            cumulative += score
            if target <= cumulative:
                return asset
        return top[-1][1]

    def resolve_primary(
        self, request: ExpressionRequest, context: ExpressionContext
    ) -> PrimaryExpression:
        now: float = self._clock()
        usage: ConversationUsage = self.history.get(context.conversation_key, now)
        ranked = self._rank(
            self.catalog.emojis,
            request,
            context,
            list(usage.recent_emojis),
            now,
        )
        selected: ExpressionAsset | None = self._choose(ranked)
        fallback: str = unicode_fallback(request.emotion)
        if selected is None:
            neutral_assets: tuple[ExpressionAsset, ...] = tuple(
                asset
                for asset in self.catalog.emojis
                if asset.emotion.value == "neutral"
            )
            selected = self._choose(
                self._rank(
                    neutral_assets,
                    request,
                    context,
                    list(usage.recent_emojis),
                    now,
                )
            )
        if selected is None:
            available: list[ExpressionAsset] = [
                asset
                for asset in self.catalog.emojis
                if self._is_available(asset, now)
            ]
            selected = available[0] if available else None
        if selected is None or selected.discord_id is None:
            return PrimaryExpression(fallback, None, fallback)
        runtime: RuntimeEmoji | None = self._runtime_emojis.get(selected.discord_id)
        if runtime is None:
            return PrimaryExpression(fallback, None, fallback)
        prefix: str = "a" if runtime.animated else ""
        rendered: str = f"<{prefix}:{runtime.name}:{runtime.discord_id}>"
        return PrimaryExpression(rendered, selected, fallback)

    def resolve_bonus(
        self, request: ExpressionRequest, context: ExpressionContext
    ) -> ExpressionAsset | None:
        if not request.allow_bonus or request.bonus_media is BonusMedia.NONE:
            return None
        now: float = self._clock()
        usage: ConversationUsage = self.history.get(context.conversation_key, now)
        recent_responses: list[float] = list(usage.response_times)
        if len(recent_responses) >= 2 and now - recent_responses[-2] <= 20.0:
            return None
        media: AssetType = self._select_bonus_type(request)
        assets: tuple[ExpressionAsset, ...]
        minimum: float
        channel_cooldown: float
        same_cooldown: float
        if media is AssetType.GIF:
            assets = self.catalog.gifs
            minimum = self.catalog.policy.gif_min_intensity
            channel_cooldown = self.catalog.policy.gif_channel_cooldown_seconds
            same_cooldown = self.catalog.policy.same_gif_cooldown_seconds
        else:
            assets = self.catalog.stickers
            minimum = self.catalog.policy.sticker_min_intensity
            channel_cooldown = self.catalog.policy.sticker_channel_cooldown_seconds
            same_cooldown = self.catalog.policy.same_sticker_cooldown_seconds
        if request.intensity < minimum or not self._bonus_intent_allowed(request, media):
            return None
        last_channel: float | None = self.history.last_channel_bonus(
            context.channel_id, media.value
        )
        if last_channel is not None and now - last_channel < channel_cooldown:
            return None
        ranked = self._rank(
            assets, request, context, list(usage.recent_bonus), now
        )
        ranked = [
            item
            for item in ranked
            if self.history.last_asset_use(item[1].key) is None
            or now - self.history.last_asset_use(item[1].key) >= same_cooldown
        ]
        selected: ExpressionAsset | None = self._choose(ranked)
        if selected is None:
            return None
        chance: float = self._bonus_chance(request, media, context.is_owner)
        return selected if self._rng.random() < chance else None

    def _select_bonus_type(self, request: ExpressionRequest) -> AssetType:
        if request.bonus_media is BonusMedia.GIF:
            return AssetType.GIF
        if request.bonus_media is BonusMedia.STICKER:
            return AssetType.STICKER
        return AssetType.GIF if request.intensity >= 0.85 else AssetType.STICKER

    @staticmethod
    def _bonus_intent_allowed(
        request: ExpressionRequest, media: AssetType
    ) -> bool:
        sticker_intents: frozenset[ExpressionIntent] = frozenset(
            {
                ExpressionIntent.CELEBRATION,
                ExpressionIntent.COMFORT,
                ExpressionIntent.AFFECTION,
                ExpressionIntent.SHOCK,
                ExpressionIntent.PLAYFUL_TEASING,
                ExpressionIntent.LIGHT_SCOLDING,
                ExpressionIntent.PRAISE,
                ExpressionIntent.REACTION,
            }
        )
        gif_intents: frozenset[ExpressionIntent] = frozenset(
            {
                ExpressionIntent.CELEBRATION,
                ExpressionIntent.COMFORT,
                ExpressionIntent.SHOCK,
                ExpressionIntent.AFFECTION,
                ExpressionIntent.REACTION,
            }
        )
        return request.intent in (gif_intents if media is AssetType.GIF else sticker_intents)

    @staticmethod
    def _bonus_chance(
        request: ExpressionRequest, media: AssetType, is_owner: bool
    ) -> float:
        if media is AssetType.GIF:
            chance: float = 0.03
            chance += 0.05 if request.intensity >= 0.8 else 0.0
            chance += 0.05 if request.intensity >= 0.9 else 0.0
            chance += 0.08 if request.bonus_media is BonusMedia.GIF else 0.0
            return min(chance, 0.20)
        chance = 0.10
        chance += 0.08 if request.intensity >= 0.65 else 0.0
        chance += 0.08 if request.intensity >= 0.8 else 0.0
        chance += 0.12 if request.bonus_media is BonusMedia.STICKER else 0.0
        chance += 0.03 if is_owner else 0.0
        return min(chance, 0.40)

    def record_primary_success(
        self, context: ExpressionContext, primary: PrimaryExpression
    ) -> None:
        now: float = self._clock()
        if primary.asset is None:
            self.history.record_unicode(context.conversation_key, now)
        else:
            self.history.record_emoji(
                context.conversation_key, primary.asset.key, now
            )

    def record_bonus_success(
        self, context: ExpressionContext, asset: ExpressionAsset
    ) -> None:
        self.history.record_bonus(
            context.conversation_key,
            context.channel_id,
            asset.key,
            asset.type.value,
            self._clock(),
        )

    def record_failure(self, asset: ExpressionAsset, reason: str) -> None:
        count: int = self._failure_counts.get(asset.key, 0) + 1
        self._failure_counts[asset.key] = count
        delays: dict[int, float] = {1: 30.0, 2: 120.0, 3: 600.0}
        self._disabled_until[asset.key] = self._clock() + delays.get(count, 3600.0)
        print(
            f"[SENNA EXPRESSION] asset failure key={asset.key} count={count} "
            f"reason={reason}"
        )
