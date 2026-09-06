import random
import unittest

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


def asset(key: str, asset_type: AssetType, emotion: Emotion, discord_id: int, guild_id: int) -> ExpressionAsset:
    return ExpressionAsset(
        key=key,
        type=asset_type,
        name=key,
        discord_id=discord_id,
        guild_id=guild_id,
        local_path=None,
        animated=False,
        emotion=emotion,
        intents=frozenset({ExpressionIntent.REACTION, ExpressionIntent.COMFORT}),
        intensity_min=0.0,
        intensity_max=1.0,
        tags=frozenset(),
        enabled=True,
        owner_affinity=0.0,
        priority=1.0,
        description=None,
        safe=True,
    )


class AutoSyncResolverSafetyTests(unittest.TestCase):
    def _resolver(self, *, emojis=(), stickers=()):
        catalog = empty_catalog()
        catalog = type(catalog)(catalog.version, catalog.policy, tuple(emojis), tuple(stickers), ())
        resolver = ExpressionResolver(
            catalog,
            ExpressionHistory(8, 5, 3600.0),
            ZeroRandom(),
            lambda: 100.0,
        )
        resolver.replace_runtime_emojis(
            [RuntimeEmoji(item.discord_id, item.name, item.guild_id or 1, False, True) for item in emojis]
        )
        return resolver

    @staticmethod
    def _context(guild_id: int) -> ExpressionContext:
        return ExpressionContext(
            ExpressionConversationKey("discord_text", guild_id, 10, None),
            guild_id,
            10,
            False,
        )

    def test_unrelated_custom_emoji_falls_back_to_unicode(self) -> None:
        wrong = asset("angry", AssetType.EMOJI, Emotion.ANGRY, 1, 1)
        resolver = self._resolver(emojis=(wrong,))
        request = ExpressionRequest(
            Emotion.HAPPY,
            ExpressionIntent.REACTION,
            0.8,
            BonusMedia.NONE,
            False,
        )
        primary = resolver.resolve_primary(request, self._context(1))
        self.assertIsNone(primary.asset)
        self.assertEqual(primary.rendered, "😊")

    def test_sticker_from_other_guild_is_not_selected(self) -> None:
        sticker = asset("comfort", AssetType.STICKER, Emotion.SAD, 99, 2)
        resolver = self._resolver(stickers=(sticker,))
        request = ExpressionRequest(
            Emotion.SAD,
            ExpressionIntent.COMFORT,
            0.9,
            BonusMedia.STICKER,
            True,
        )
        self.assertIsNone(resolver.resolve_bonus(request, self._context(1)))


if __name__ == "__main__":
    unittest.main()
