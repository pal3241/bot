import unittest

from assistant.discord.message_classifier import (
    MessageAction,
    MessageFacts,
    SessionCommand,
    classify_message,
)
from assistant.session import SessionState


def facts(
    content: str,
    mentioned: bool,
    is_reply: bool,
    reply_resolved: bool,
    replied_to_bot: bool,
    state: SessionState,
    author_is_bot: bool,
) -> MessageFacts:
    return MessageFacts(
        author_is_bot=author_is_bot,
        mentioned_bot=mentioned,
        is_reply=is_reply,
        reply_resolved=reply_resolved,
        replied_to_bot=replied_to_bot,
        content=content,
        session_state=state,
    )


class MessageClassifierTests(unittest.TestCase):
    def test_mention_responds_and_overrides_reply_to_other(self) -> None:
        decision = classify_message(
            facts("menurut lu?", True, True, True, False, SessionState.INACTIVE, False)
        )
        self.assertEqual(decision.action, MessageAction.RESPOND)
        self.assertEqual(decision.reason, "explicit_mention")

    def test_reply_to_other_and_unresolved_reply_are_ignored(self) -> None:
        other = classify_message(
            facts("bakso", False, True, True, False, SessionState.ACTIVE, False)
        )
        unresolved = classify_message(
            facts("bakso", False, True, False, False, SessionState.ACTIVE, False)
        )
        self.assertEqual(other.action, MessageAction.IGNORE)
        self.assertEqual(unresolved.action, MessageAction.IGNORE)

    def test_reply_to_sena_responds(self) -> None:
        decision = classify_message(
            facts("contohnya?", False, True, True, True, SessionState.ACTIVE, False)
        )
        self.assertEqual(decision.action, MessageAction.RESPOND)

    def test_normal_active_is_context_only_and_inactive_is_ignored(self) -> None:
        active = classify_message(
            facts("gue gak suka", False, False, True, False, SessionState.ACTIVE, False)
        )
        inactive = classify_message(
            facts("gue gak suka", False, False, True, False, SessionState.INACTIVE, False)
        )
        self.assertEqual(active.action, MessageAction.CONTEXT_ONLY)
        self.assertEqual(inactive.action, MessageAction.IGNORE)

    def test_bot_message_is_ignored(self) -> None:
        decision = classify_message(
            facts("Sena halo", True, False, True, False, SessionState.ACTIVE, True)
        )
        self.assertEqual(decision.action, MessageAction.IGNORE)

    def test_direct_address_only_matches_at_start(self) -> None:
        direct = classify_message(
            facts("Hey Sena bantu", False, False, True, False, SessionState.INACTIVE, False)
        )
        substring = classify_message(
            facts("kemarin lihat sena di sana", False, False, True, False, SessionState.INACTIVE, False)
        )
        self.assertEqual(direct.action, MessageAction.RESPOND)
        self.assertEqual(direct.cleaned_text, "bantu")
        self.assertEqual(substring.action, MessageAction.IGNORE)

    def test_silence_and_wake_commands_are_local(self) -> None:
        silence = classify_message(
            facts("diam dulu", True, False, True, False, SessionState.ACTIVE, False)
        )
        wake = classify_message(
            facts("Sen bangun", False, False, True, False, SessionState.SILENCED, False)
        )
        self.assertEqual(silence.command, SessionCommand.SILENCE)
        self.assertEqual(wake.command, SessionCommand.WAKE)


if __name__ == "__main__":
    unittest.main()
