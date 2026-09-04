import unittest

from actions.parser import parse_action_response
from core.structured_response import sanitize_visible_text
from memory.context import build_identity_context, enforce_owner_addressing
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

    def test_pipe_separated_short_expression_metadata_is_removed(self) -> None:
        raw = "jawaban aman.\nEmotion: affection | Intent: playful\\_teasing | Intensity: 0.5"
        self.assertEqual(sanitize_visible_text(raw), "jawaban aman.")

    def test_multiline_expression_block_is_removed(self) -> None:
        raw = (
            "aman.\nExpression:\n"
            "emotion: happy\nintent: reaction\nintensity: 0.8\n"
            "bonus_media: none\nallow_bonus: false"
        )
        self.assertEqual(sanitize_visible_text(raw), "aman.")

    def test_flattened_current_speaker_echo_is_removed(self) -> None:
        raw = (
            "[CURRENT SPEAKER] Banuy | id=1286683942887362633 "
            "[Current message] Berhenti manggil aku sayang dong, nanti pembuat mu marah "
            "Emotion: affection | Intent: playful\\_teasing | Intensity: 0.5"
        )
        self.assertEqual(sanitize_visible_text(raw), "")

    def test_multiline_current_speaker_and_message_payload_are_removed(self) -> None:
        raw = (
            "[Current speaker]\nBanuy | id=1286683942887362633\n"
            "[Current message]\nBerhenti manggil aku sayang dong\n"
            "jawaban asli setelah metadata"
        )
        self.assertEqual(sanitize_visible_text(raw), "jawaban asli setelah metadata")

    def test_action_tag_is_removed_from_visible_text(self) -> None:
        raw = "oke gue masuk. <action>[voice.join_user]</action>"
        self.assertEqual(sanitize_visible_text(raw), "oke gue masuk.")

    def test_action_tag_only_becomes_empty_visible_text(self) -> None:
        raw = "<action>[voice.join_user]</action>"
        self.assertEqual(sanitize_visible_text(raw), "")

    def test_normal_prose_about_emotions_is_preserved(self) -> None:
        raw = "Emotion itu normal; intensity perasaan bisa berubah."
        self.assertEqual(sanitize_visible_text(raw), raw)


class TaggedActionFallbackTests(unittest.TestCase):
    def test_tagged_voice_join_is_recovered_as_action(self) -> None:
        actions = parse_action_response("<action>[voice.join_user]</action>")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].tool, "voice.join_user")
        self.assertEqual(actions[0].arguments, {})

    def test_json_actions_remain_primary(self) -> None:
        raw = (
            '{"text":"oke","actions":[{"tool":"voice.leave","arguments":{}}]}'
            '<action>[voice.join_user]</action>'
        )
        actions = parse_action_response(raw)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].tool, "voice.leave")


class OwnerContextTests(unittest.TestCase):
    def test_authenticated_owner_has_boss_address_and_father_daughter_relationship(self) -> None:
        owner = OwnerResolver(123).resolve(123, "Fahri")
        context = build_identity_context(owner, [])
        self.assertIn("preferred spoken title for him is 'boss'", context)
        self.assertIn("relationship is father/daughter", context)
        self.assertIn("Never seriously insult", context)
        self.assertIn("authenticated by Discord user ID", context)

    def test_non_owner_gets_explicit_owner_title_boundary(self) -> None:
        user = OwnerResolver(123).resolve(456, "Fahri")
        context = build_identity_context(user, [])
        self.assertIn("NOT Sena's configured owner", context)
        self.assertIn("'boss' is reserved exclusively", context)
        self.assertNotIn("OWNER RELATIONSHIP - HIGH PRIORITY", context)

    def test_owner_boss_address_is_preserved(self) -> None:
        owner = OwnerResolver(123).resolve(123, "Fahri")
        self.assertEqual(
            enforce_owner_addressing("iya boss, langsung gue cek.", owner),
            "iya boss, langsung gue cek.",
        )

    def test_non_owner_direct_boss_address_is_removed(self) -> None:
        user = OwnerResolver(123).resolve(456, "Banuy")
        self.assertEqual(
            enforce_owner_addressing("iya boss, nanti gue cek.", user),
            "iya, nanti gue cek.",
        )
        self.assertEqual(
            enforce_owner_addressing("boss, sini dulu.", user),
            "sini dulu.",
        )

    def test_non_owner_can_still_discuss_a_boss_as_a_noun(self) -> None:
        user = OwnerResolver(123).resolve(456, "Banuy")
        text = "Kalau boss kamu marah, jelaskan situasinya dulu."
        self.assertEqual(enforce_owner_addressing(text, user), text)


if __name__ == "__main__":
    unittest.main()