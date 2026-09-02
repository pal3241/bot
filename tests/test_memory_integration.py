import tempfile
import unittest
from pathlib import Path

from assistant.llm.base import ChatMessage, LLMProvider
from assistant.llm.manager import LLMManager
from assistant.manager import AssistantManager
from assistant.personality import PersonalityManager
from assistant.session import SessionManager
from assistant.settings import AISettings
from memory.identity import OwnerResolver
from memory.manager import MemoryManager
from memory.policy import MemoryPolicy
from memory.store import MemoryStore


class SequenceProvider(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses: list[str] = list(responses)
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages: list[ChatMessage], model: str) -> str:
        self.calls.append(list(messages))
        if not self._responses:
            raise RuntimeError("Response test provider habis.")
        return self._responses.pop(0)

    async def close(self) -> None:
        return


def ai_settings() -> AISettings:
    return AISettings(
        "openrouter",
        "model",
        "model",
        "https://example.com/v1",
        300,
        60.0,
        2,
        1.0,
        120.0,
        24,
    )


def build_manager(
    folder: str, provider: SequenceProvider, owner_id: int
) -> AssistantManager:
    return AssistantManager(
        PersonalityManager(Path(folder) / "personality.json"),
        SessionManager(120.0, 24),
        LLMManager(provider, "test", "model"),
        ai_settings(),
        OwnerResolver(owner_id),
        MemoryManager(
            MemoryStore(Path(folder) / "memory.db"),
            MemoryPolicy(0.55, 0.70, 500),
            5,
            2500,
        ),
    )


class MemoryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_memory_survives_restart_and_private_context_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            first_provider = SequenceProvider(
                ['{"text":"oke, gue inget","memory":null}']
            )
            first = build_manager(folder, first_provider, 123)
            await first.initialize()
            await first.chat(
                123,
                "Fahri",
                10,
                "ingat bahwa gue lebih suka Python",
                1,
                "discord_text",
            )
            self.assertEqual(await first.memory.count_active(123), 1)
            await first.close()

            second_provider = SequenceProvider(
                [
                    '{"text":"pakai Python","memory":null}',
                    "gue gak punya akses ke memory private owner",
                ]
            )
            second = build_manager(folder, second_provider, 123)
            await second.initialize()
            await second.chat(
                123,
                "Fahri",
                11,
                "bahasa apa untuk project baru?",
                1,
                "discord_text",
            )
            owner_prompt: str = "\n".join(
                message.content for message in second_provider.calls[0]
            )
            self.assertIn("[RELATIONSHIP]", owner_prompt)
            self.assertIn("gue lebih suka Python", owner_prompt)

            await second.chat(
                456,
                "User2",
                12,
                "owner sukanya bahasa apa?",
                1,
                "discord_text",
            )
            user_prompt: str = "\n".join(
                message.content for message in second_provider.calls[1]
            )
            self.assertNotIn("[RELATIONSHIP]", user_prompt)
            self.assertNotIn("gue lebih suka Python", user_prompt)
            await second.close()

    async def test_database_failure_does_not_break_normal_chat(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            provider = SequenceProvider(["normal response"])
            manager = AssistantManager(
                PersonalityManager(Path(folder) / "personality.json"),
                SessionManager(120.0, 24),
                LLMManager(provider, "test", "model"),
                ai_settings(),
                OwnerResolver(None),
                MemoryManager(
                    MemoryStore(Path(folder)),
                    MemoryPolicy(0.55, 0.70, 500),
                    5,
                    2500,
                ),
            )
            await manager.initialize()
            response = await manager.chat(
                456, "User", 10, "halo", 1, "discord_text"
            )
            self.assertEqual(response.text, "normal response")
            await manager.close()


if __name__ == "__main__":
    unittest.main()
