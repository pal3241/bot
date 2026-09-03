import unittest

from core.structured_response import sanitize_visible_text
from memory.context import build_identity_context
from memory.identity import OwnerResolver


class StructuredResponseFirewallTests(unittest.TestCase):
    def test_expression_metadata_line_is_removed(self) -> None:
        raw = (
            "iya, santai boss.\n"
            "Expression: emotion=teasing, intent=playful_teasing, intensity=0.5, "
            "bonus_media=auto, allow_bonus=true"
        )
        self.assertEqual(sanitize_visible_text(raw), "iya, santai boss.")

    def test_escaped_underscore_metadata_is_removed(self) -> None:
        raw = (
            "oke.\n"
            "Expression: emotion=teasing, intent=playful\\_teasing, intensity=0.5, "
            "bonus\\_media=auto, allow\\_bonus=true"
        )
        self.assertEqual(sanitize_visible_text(raw), "oke.")

    def test_multiline_expression_block_is_removed(self) -> None:
        raw = (
            "aman.\nExpression:\n"
            "emotion: happy\nintent: reaction\nintensity: 0.8\n"
            "bonus_media: none\nallow_bonus: false"
        )
        self.assertEqual(sanitize_visible_text(raw), "aman.")

    def test_normal_prose_about_emotions_is_preserved(self) -> None:
        raw = "Emotion itu normal; intensity perasaan bisa berubah."
        self.assertEqual(sanitize_visible_text(raw), raw)


class OwnerContextTests(unittest.TestCase):
    def test_authenticated_owner_has_boss_address_and_respect_guardrails(self) -> None:
        owner = OwnerResolver(123).resolve(123, "Fahri")
        context = build_identity_context(owner, [])
        self.assertIn("preferred spoken address is 'boss'", context)
        self.assertIn("Never seriously insult", context)
        self.assertIn("authenticated by Discord user ID", context)

    def test_non_owner_does_not_receive_owner_relationship_context(self) -> None:
        user = OwnerResolver(123).resolve(456, "Fahri")
        context = build_identity_context(user, [])
        self.assertNotIn("preferred spoken address is 'boss'", context)
        self.assertNotIn("OWNER RELATIONSHIP", context)


if __name__ == "__main__":
    unittest.main()
