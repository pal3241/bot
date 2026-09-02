import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from assistant.personality import (
    DEFAULT_PERSONALITY,
    PersonalityManager,
    build_system_prompt,
    load_personality,
    parse_personality,
    save_personality,
)


class PersonalitySystemTests(unittest.TestCase):
    def test_default_prompt_is_compact_and_multilingual(self) -> None:
        prompt: str = build_system_prompt(DEFAULT_PERSONALITY)
        self.assertGreaterEqual(len(prompt.split()), 100)
        self.assertLessEqual(len(prompt.split()), 300)
        self.assertIn("Detect the latest user's language", prompt)

    def test_invalid_controlled_values_use_field_defaults(self) -> None:
        raw: dict[str, object] = {
            "name": "SENA",
            "identity": {"description": "AI", "role": "teman"},
            "style": {
                "tone": "unknown",
                "energy": "medium",
                "humor": "medium",
                "friendliness": "high",
                "formality": "low",
                "response_length": "SUPER_LONGGG",
                "emoji_usage": "low",
            },
            "language": {
                "mode": "auto",
                "default": "id",
                "match_user_language": True,
            },
            "behavior": {
                "natural_conversation": True,
                "avoid_repeating_user": True,
                "avoid_overexplaining": True,
                "avoid_robotic_phrasing": True,
                "ask_followup_when_useful": True,
            },
        }
        parsed = parse_personality(raw)
        self.assertEqual(parsed.style.tone, DEFAULT_PERSONALITY.style.tone)
        self.assertEqual(parsed.style.response_length, "short")

    def test_broken_json_uses_default(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path: Path = Path(folder) / "personality.json"
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual(load_personality(path), DEFAULT_PERSONALITY)

    def test_missing_file_uses_default(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path: Path = Path(folder) / "missing.json"
            self.assertEqual(load_personality(path), DEFAULT_PERSONALITY)

    def test_emoji_none_and_very_short_affect_prompt(self) -> None:
        config = replace(
            DEFAULT_PERSONALITY,
            style=replace(
                DEFAULT_PERSONALITY.style,
                response_length="very_short",
                emoji_usage="none",
            ),
        )
        prompt: str = build_system_prompt(config)
        self.assertIn("Use 1-2 sentences.", prompt)
        self.assertIn("Do not use emoji.", prompt)

    def test_identity_has_prompt_injection_protection(self) -> None:
        prompt: str = build_system_prompt(DEFAULT_PERSONALITY)
        self.assertIn("Identity is system-controlled", prompt)
        self.assertIn("never permanently change your name", prompt)

    def test_update_and_reload_persist_config(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path: Path = Path(folder) / "personality.json"
            save_personality(path, DEFAULT_PERSONALITY)
            manager: PersonalityManager = PersonalityManager(path)
            changed = replace(
                manager.config,
                style=replace(manager.config.style, tone="playful"),
            )
            manager.update(changed)
            manager.reload()
            self.assertEqual(manager.config.style.tone, "playful")


if __name__ == "__main__":
    unittest.main()
