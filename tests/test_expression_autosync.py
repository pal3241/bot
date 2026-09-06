import unittest
from dataclasses import replace

from expression.autosync import auto_sync_catalog
from expression.enums import AssetType, Emotion, ExpressionIntent
from expression.loader import empty_catalog
from expression.models import ExpressionAsset


class FakeEmoji:
    def __init__(self, emoji_id: int, name: str, guild_id: int, *, animated: bool = False, available: bool = True) -> None:
        self.id = emoji_id
        self.name = name
        self.guild_id = guild_id
        self.animated = animated
        self.available = available


class FakeSticker:
    def __init__(self, sticker_id: int, name: str, guild_id: int, description: str = "") -> None:
        self.id = sticker_id
        self.name = name
        self.guild_id = guild_id
        self.description = description
        self.emoji = None


class FakeGuild:
    def __init__(self, stickers) -> None:
        self.stickers = stickers


class FakeClient:
    def __init__(self, emojis, guilds) -> None:
        self.emojis = emojis
        self.guilds = guilds


def manual_emoji(emoji_id: int) -> ExpressionAsset:
    return ExpressionAsset(
        key=f"manual:{emoji_id}",
        type=AssetType.EMOJI,
        name="manual",
        discord_id=emoji_id,
        guild_id=1,
        local_path=None,
        animated=False,
        emotion=Emotion.HAPPY,
        intents=frozenset({ExpressionIntent.REACTION}),
        intensity_min=0.0,
        intensity_max=1.0,
        tags=frozenset(),
        enabled=True,
        owner_affinity=0.0,
        priority=1.0,
        description=None,
        safe=True,
    )


class ExpressionAutoSyncTests(unittest.TestCase):
    def test_discovers_runtime_assets_and_manual_entries_win(self) -> None:
        base = replace(empty_catalog(), emojis=(manual_emoji(1),))
        client = FakeClient(
            [
                FakeEmoji(1, "duplicate_happy", 1),
                FakeEmoji(2, "zeta_happy", 1, animated=True),
                FakeEmoji(3, "unavailable", 1, available=False),
            ],
            [FakeGuild([FakeSticker(10, "big_hug", 1, "cute love")])],
        )
        merged, stats = auto_sync_catalog(base, client)  # type: ignore[arg-type]

        self.assertEqual(stats.emojis_added, 1)
        self.assertEqual(stats.stickers_added, 1)
        self.assertEqual(len(merged.emojis), 2)
        self.assertEqual(len(merged.stickers), 1)

        auto_emoji = next(item for item in merged.emojis if item.discord_id == 2)
        self.assertEqual(auto_emoji.emotion, Emotion.HAPPY)
        self.assertTrue(auto_emoji.animated)
        self.assertIn(ExpressionIntent.REACTION, auto_emoji.intents)

        sticker = merged.stickers[0]
        self.assertEqual(sticker.emotion, Emotion.AFFECTIONATE)
        self.assertEqual(sticker.guild_id, 1)

    def test_unknown_name_is_neutral_reaction(self) -> None:
        merged, _ = auto_sync_catalog(
            empty_catalog(),
            FakeClient([FakeEmoji(5, "custom_asset_42", 9)], []),  # type: ignore[arg-type]
        )
        self.assertEqual(merged.emojis[0].emotion, Emotion.NEUTRAL)
        self.assertEqual(merged.emojis[0].intents, frozenset({ExpressionIntent.REACTION}))


if __name__ == "__main__":
    unittest.main()
