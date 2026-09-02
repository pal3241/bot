import time
import unittest

from assistant.conversation import (
    ConversationEntry,
    ConversationKey,
    build_conversation_key,
    format_history,
)
from assistant.session import SessionManager, SessionState


def entry(user_id: int, display_name: str, content: str) -> ConversationEntry:
    return ConversationEntry("user", content, user_id, display_name, time.time())


class SharedSessionTests(unittest.TestCase):
    def test_text_shared_voice_per_user(self) -> None:
        text_one = build_conversation_key("discord_text", 1, 10, 100)
        text_two = build_conversation_key("discord_text", 1, 10, 200)
        voice_one = build_conversation_key("discord_voice", 1, 10, 100)
        voice_two = build_conversation_key("discord_voice", 1, 10, 200)
        self.assertEqual(text_one, text_two)
        self.assertNotEqual(voice_one, voice_two)

    def test_peek_does_not_create_session(self) -> None:
        sessions = SessionManager(120.0, 24)
        key = ConversationKey("discord_text", 1, 10, None)
        self.assertIsNone(sessions.peek(key))
        self.assertEqual(sessions.state(key), SessionState.INACTIVE)
        self.assertIsNone(sessions.peek(key))

    def test_channel_guild_and_dm_are_isolated(self) -> None:
        keys = {
            ConversationKey("discord_text", 1, 10, None),
            ConversationKey("discord_text", 1, 11, None),
            ConversationKey("discord_text", 2, 10, None),
            ConversationKey("discord_text", None, 10, None),
        }
        self.assertEqual(len(keys), 4)

    def test_timeout_removes_session_and_history(self) -> None:
        sessions = SessionManager(0.01, 24)
        key = ConversationKey("discord_text", 1, 10, None)
        session = sessions.activate(key)
        sessions.add_history(session, [entry(100, "User1", "halo")])
        session.last_activity -= 1.0
        self.assertIsNone(sessions.peek(key))
        self.assertEqual(session.history, [])

    def test_history_is_trimmed(self) -> None:
        sessions = SessionManager(120.0, 2)
        key = ConversationKey("discord_text", 1, 10, None)
        session = sessions.activate(key)
        sessions.add_history(
            session,
            [entry(1, "Satu", "1"), entry(2, "Dua", "2"), entry(3, "Tiga", "3")],
        )
        self.assertEqual([item.content for item in session.history], ["2", "3"])

    def test_silence_clears_shared_history_and_wake_activates(self) -> None:
        sessions = SessionManager(120.0, 24)
        key = ConversationKey("discord_text", 1, 10, None)
        session = sessions.activate(key)
        sessions.add_history(session, [entry(1, "Satu", "halo")])
        sessions.silence(key)
        self.assertEqual(sessions.state(key), SessionState.SILENCED)
        self.assertEqual(session.history, [])
        sessions.activate(key)
        self.assertEqual(sessions.state(key), SessionState.ACTIVE)

    def test_speaker_labels_remain_distinct(self) -> None:
        history: str = format_history(
            [entry(100, "User1", "halo"), entry(200, "User2", "hai")]
        )
        self.assertIn("[User1 | id=100]", history)
        self.assertIn("[User2 | id=200]", history)


if __name__ == "__main__":
    unittest.main()
