import json
import tempfile
import unittest
from pathlib import Path

from expression.exceptions import ExpressionCatalogError
from expression.loader import load_catalog


def base_catalog() -> dict[str, object]:
    return {
        "version": 1,
        "policy": {
            "emoji_required": True,
            "unicode_fallback_enabled": True,
            "top_k": 3,
            "min_candidate_score": 0.42,
            "top_k_score_window": 0.12,
            "sticker_min_intensity": 0.55,
            "gif_min_intensity": 0.75,
            "sticker_channel_cooldown_seconds": 15,
            "gif_channel_cooldown_seconds": 30,
            "same_sticker_cooldown_seconds": 120,
            "same_gif_cooldown_seconds": 180,
            "recent_emoji_size": 8,
            "recent_bonus_size": 5,
        },
        "emojis": [],
        "stickers": [],
        "gifs": [],
    }


def emoji(key: str, discord_id: int, emotion: str) -> dict[str, object]:
    return {
        "key": key,
        "name": key,
        "discord_id": discord_id,
        "guild_id": 1,
        "animated": False,
        "emotion": emotion,
        "intents": ["reaction"],
        "intensity_min": 0.0,
        "intensity_max": 1.0,
        "tags": [],
        "enabled": True,
        "owner_affinity": 0.0,
        "priority": 1.0,
    }


class ExpressionCatalogTests(unittest.TestCase):
    def test_valid_and_invalid_individual_asset(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            catalog_data = base_catalog()
            catalog_data["emojis"] = [
                emoji("happy", 1, "happy"),
                emoji("broken", 2, "unknown"),
            ]
            path = root / "expressions.json"
            path.write_text(json.dumps(catalog_data), encoding="utf-8")
            catalog = load_catalog(path, root)
            self.assertEqual(len(catalog.emojis), 1)

    def test_missing_invalid_json_and_version_raise_root_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ExpressionCatalogError):
                load_catalog(root / "missing.json", root)
            invalid = root / "invalid.json"
            invalid.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ExpressionCatalogError):
                load_catalog(invalid, root)
            data = base_catalog()
            data["version"] = 2
            invalid.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ExpressionCatalogError):
                load_catalog(invalid, root)

    def test_duplicate_and_path_traversal_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = base_catalog()
            data["emojis"] = [emoji("same", 1, "happy"), emoji("same", 2, "happy")]
            data["gifs"] = [
                {
                    **emoji("escape", 3, "happy"),
                    "local_path": "../outside.gif",
                }
            ]
            path = root / "expressions.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            catalog = load_catalog(path, root)
            self.assertEqual(len(catalog.emojis), 1)
            self.assertEqual(catalog.gifs, ())


if __name__ == "__main__":
    unittest.main()
