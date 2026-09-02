import tempfile
import unittest
from pathlib import Path

from assistant.conversation import build_conversation_key
from assistant.llm.base import ChatMessage, LLMProvider
from assistant.llm.manager import LLMManager
from assistant.manager import AssistantManager
from assistant.personality import PersonalityManager
from assistant.session import SessionManager
from assistant.settings import AISettings


class RecordingProvider(LLMProvider):
    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages: list[ChatMessage], model: str) -> str:
        self.calls.append(list(messages))
        return "jawaban"

    async def close(self) -> None:
        return


def settings() -> AISettings:
    return AISettings(
        provider_name="openrouter",
        openrouter_model="model",
        nvidia_nim_model="model",
        nvidia_nim_base_url="https://example.com/v1",
        max_tokens=300,
        request_timeout_seconds=60.0,
        retry_count=2,
        retry_delay_seconds=1.0,
        chat_timeout_seconds=120.0,
        history_max_messages=24,
    )


class AssistantManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_context_only_does_not_call_llm_and_is_visible_to_next_user(self) -> None:
        provider = RecordingProvider()
        with tempfile.TemporaryDirectory() as folder:
            manager = AssistantManager(
                personality=PersonalityManager(Path(folder) / "personality.json"),
                sessions=SessionManager(120.0, 24),
                llm=LLMManager(provider, "test", "model"),
                settings=settings(),
            )
            key = build_conversation_key("discord_text", 1, 10, 100)
            manager.sessions.activate(key)
            await manager.observe_message(100, "User1", 10, "gue gak suka", 1, "discord_text")
            self.assertEqual(provider.calls, [])

            await manager.chat(200, "User2", 10, "kenapa dia?", 1, "discord_text")
            self.assertEqual(len(provider.calls), 1)
            prompt: str = "\n".join(message.content for message in provider.calls[0])
            self.assertIn("[User1 | id=100]", prompt)
            self.assertIn("[Current speaker]\nUser2 | id=200", prompt)
            await manager.close()

    async def test_two_text_users_share_history_without_duplicate_current_message(self) -> None:
        provider = RecordingProvider()
        with tempfile.TemporaryDirectory() as folder:
            manager = AssistantManager(
                personality=PersonalityManager(Path(folder) / "personality.json"),
                sessions=SessionManager(120.0, 24),
                llm=LLMManager(provider, "test", "model"),
                settings=settings(),
            )
            await manager.chat(100, "User1", 10, "halo", 1, "discord_text")
            await manager.chat(200, "User2", 10, "bilang dia stres", 1, "discord_text")
            second_prompt: str = "\n".join(
                message.content for message in provider.calls[1]
            )
            self.assertIn("[User1 | id=100]\nhalo", second_prompt)
            self.assertEqual(second_prompt.count("bilang dia stres"), 1)
            await manager.close()


if __name__ == "__main__":
    unittest.main()
