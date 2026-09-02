import random
import unittest
from dataclasses import replace
from pathlib import Path

from expression.enums import AssetType, BonusMedia, Emotion, ExpressionIntent
from expression.history import ExpressionHistory
from expression.loader import empty_catalog
from expression.models import (
    ExpressionAsset,
    ExpressionConversationKey,
    ExpressionContext,
    ExpressionRequest,
    RuntimeEmoji,
)
from expression.resolver import ExpressionResolver


class ZeroRandom(random.Random):
    def random(self) -> float:
        return 0.0


def asset(
    key: str,
    asset_type: AssetType,
    emotion: Emotion,
    discord_id: int | None,
    owner_affinity: float,
) -> ExpressionAsset:
    return ExpressionAsset(
        key=key,
        type=asset_type,
        name=key,
        discord_id=discord_id,
        guild_id=1,
        local_path=Path("unused.gif") if asset_type is AssetType.GIF else None,
        animated=False,
        emotion=emotion,
        intents=frozenset({ExpressionIntent.REACTION, ExpressionIntent.PRAISE}),
        intensity_min=0.0,
        intensity_max=1.0,
        tags=frozenset(),
        enabled=True,
        owner_affinity=owner_affinity,
        priority=1.0,
        description=None,
        safe=True,
    )


class ExpressionResolverTests(unittest.TestCase):
    def build_resolver(
        self,
        emojis: tuple[ExpressionAsset, ...],
        stickers: tuple[ExpressionAsset, ...],
    ) -> tuple[ExpressionResolver, list[float]]:
        catalog = replace(empty_catalog(), emojis=emojis, stickers=stickers)
        clock: list[float] = [100.0]
        resolver = ExpressionResolver(
            catalog,
            ExpressionHistory(8, 5, 3600.0),
            ZeroRandom(),
            lambda: clock[0],
        )
        resolver.replace_runtime_emojis(
            [
                RuntimeEmoji(item.discord_id, item.name, 1, False, True)
                for item in emojis
                if item.discord_id is not None
            ]
        )
        return resolver, clock

    def context(self, is_owner: bool) -> ExpressionContext:
        return ExpressionContext(
            ExpressionConversationKey("discord_text", 1, 10, None),
            1,
            10,
            is_owner,
        )

    def test_exact_semantic_wins_and_recent_asset_is_penalized(self) -> None:
        first = asset("happy_1", AssetType.EMOJI, Emotion.HAPPY, 1, 0.0)
        second = asset("happy_2", AssetType.EMOJI, Emotion.HAPPY, 2, 0.0)
        sad = asset("sad", AssetType.EMOJI, Emotion.SAD, 3, 0.0)
        resolver, clock = self.build_resolver((first, second, sad), ())
        request = ExpressionRequest(
            Emotion.HAPPY, ExpressionIntent.REACTION, 0.5, BonusMedia.NONE, False
        )
        selected_one = resolver.resolve_primary(request, self.context(False))
        self.assertIn(selected_one.asset, {first, second})
        resolver.record_primary_success(self.context(False), selected_one)
        clock[0] += 1.0
        selected_two = resolver.resolve_primary(request, self.context(False))
        self.assertIsNotNone(selected_two.asset)
        self.assertNotEqual(selected_one.asset, selected_two.asset)

    def test_unicode_fallback_and_owner_affinity_cannot_override_semantics(self) -> None:
        resolver, _ = self.build_resolver((), ())
        request = ExpressionRequest(
            Emotion.CONCERNED,
            ExpressionIntent.REACTION,
            0.8,
            BonusMedia.NONE,
            False,
        )
        self.assertEqual(resolver.resolve_primary(request, self.context(False)).rendered, "😟")

        wrong = asset("owner_happy", AssetType.EMOJI, Emotion.HAPPY, 1, 1.0)
        correct = asset("concerned", AssetType.EMOJI, Emotion.CONCERNED, 2, 0.0)
        resolver, _ = self.build_resolver((wrong, correct), ())
        self.assertEqual(
            resolver.resolve_primary(request, self.context(True)).asset,
            correct,
        )

    def test_sticker_threshold_and_cooldown(self) -> None:
        sticker = asset("praise", AssetType.STICKER, Emotion.PROUD, 99, 0.0)
        resolver, clock = self.build_resolver((), (sticker,))
        low = ExpressionRequest(
            Emotion.PROUD, ExpressionIntent.PRAISE, 0.2, BonusMedia.STICKER, True
        )
        high = replace(low, intensity=0.9)
        self.assertIsNone(resolver.resolve_bonus(low, self.context(False)))
        selected = resolver.resolve_bonus(high, self.context(False))
        self.assertEqual(selected, sticker)
        if selected is None:
            self.fail("Sticker eligible tidak terpilih.")
        resolver.record_bonus_success(self.context(False), selected)
        clock[0] += 1.0
        self.assertIsNone(resolver.resolve_bonus(high, self.context(False)))


if __name__ == "__main__":
    unittest.main()
