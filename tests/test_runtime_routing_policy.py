import unittest
from unittest.mock import patch

from assistant.llm.base import ChatMessage, LLMProvider
from assistant.llm.routing import ModelTarget, RoutingTier
from assistant.routing_runtime_policy import build_configured_llm_manager
from assistant.settings import AISettings


class _FakeProvider(LLMProvider):
    async def chat(self, messages: list[ChatMessage], model: str) -> str:
        del messages, model
        return '{"text":"ok"}'

    async def close(self) -> None:
        return None


class RuntimeRoutingPolicyTests(unittest.TestCase):
    def _settings(self) -> AISettings:
        return AISettings(
            provider_name="nvidia_nim",
            openrouter_model="openrouter/free",
            nvidia_nim_model="nvidia/primary",
            nvidia_nim_base_url="https://example.test/v1",
            max_tokens=400,
            request_timeout_seconds=60.0,
            retry_count=0,
            retry_delay_seconds=0.0,
            chat_timeout_seconds=120.0,
            history_max_messages=20,
            routing_enabled=True,
            fast_provider="nvidia_nim",
            fast_model="nvidia/fast",
            standard_provider="nvidia_nim",
            standard_model="nvidia/standard",
            complex_provider="nvidia_nim",
            complex_model="nvidia/complex",
            fallback_provider="nvidia_nim",
            fallback_model="nvidia/fallback",
        )

    def test_all_nvidia_routes_are_not_rewritten_to_openrouter(self) -> None:
        provider = _FakeProvider()
        with patch(
            "assistant.routing_runtime_policy.create_provider",
            return_value=provider,
        ):
            manager = build_configured_llm_manager(self._settings())

        self.assertEqual(
            manager._routes[RoutingTier.FAST],
            ModelTarget("nvidia_nim", "nvidia/fast"),
        )
        self.assertEqual(
            manager._routes[RoutingTier.STANDARD],
            ModelTarget("nvidia_nim", "nvidia/standard"),
        )
        self.assertEqual(
            manager._routes[RoutingTier.COMPLEX],
            ModelTarget("nvidia_nim", "nvidia/complex"),
        )
        self.assertNotIn("openrouter", manager._providers)

    def test_nvidia_fast_and_standard_use_request_timeout(self) -> None:
        with patch(
            "assistant.routing_runtime_policy.create_provider",
            return_value=_FakeProvider(),
        ):
            manager = build_configured_llm_manager(self._settings())

        self.assertEqual(manager._tier_timeout_seconds[RoutingTier.FAST], 60.0)
        self.assertEqual(manager._tier_timeout_seconds[RoutingTier.STANDARD], 60.0)
        self.assertEqual(
            manager._tier_fallback_targets[RoutingTier.STANDARD],
            (
                ModelTarget("nvidia_nim", "nvidia/fallback"),
                ModelTarget("nvidia_nim", "nvidia/primary"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
