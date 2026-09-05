import unittest

from assistant.llm.base import ChatMessage, LLMProvider, LLMProviderError
from assistant.llm.manager import LLMManager
from assistant.llm.providers.nvidia_nim import NvidiaNimProvider
from assistant.llm.routing import ModelTarget, RoutingTier, choose_routing_tier


class FakeProvider(LLMProvider):
    def __init__(self, response: str = "ok", fail: bool = False) -> None:
        self.response = response
        self.fail = fail
        self.models: list[str] = []
        self.closed = False

    async def chat(self, messages: list[ChatMessage], model: str) -> str:
        del messages
        self.models.append(model)
        if self.fail:
            raise LLMProviderError("provider gagal")
        return self.response

    async def close(self) -> None:
        self.closed = True


class AdvancedProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, object] = {}

    async def chat_with_options(
        self,
        messages: list[ChatMessage],
        model: str,
        **options: object,
    ) -> str:
        del messages
        self.models.append(model)
        self.options = options
        return '{"text":"ok"}'


class RoutingClassifierTests(unittest.TestCase):
    def test_short_message_uses_fast_route(self) -> None:
        self.assertIs(
            choose_routing_tier(
                "halo sena",
                action_planning=False,
                memory_planning=False,
                time_context=False,
                history_chars=0,
            ),
            RoutingTier.FAST,
        )

    def test_coding_question_uses_complex_route(self) -> None:
        self.assertIs(
            choose_routing_tier(
                "jelaskan error Python ini",
                action_planning=False,
                memory_planning=False,
                time_context=False,
                history_chars=0,
            ),
            RoutingTier.COMPLEX,
        )

    def test_action_planning_uses_complex_route(self) -> None:
        self.assertIs(
            choose_routing_tier(
                "putar lagu nanti",
                action_planning=True,
                memory_planning=False,
                time_context=True,
                history_chars=0,
            ),
            RoutingTier.COMPLEX,
        )


class LLMManagerRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_complex_route_uses_kimi_k3(self) -> None:
        primary = FakeProvider()
        nim = FakeProvider(response='{"text":"complex"}')
        manager = LLMManager(
            primary,
            "openrouter",
            "fast-model",
            providers={"openrouter": primary, "nvidia_nim": nim},
            routes={
                RoutingTier.COMPLEX: ModelTarget(
                    "nvidia_nim",
                    "moonshotai/kimi-k3",
                )
            },
        )
        response = await manager.chat(
            [ChatMessage("user", "debug kode")],
            tier=RoutingTier.COMPLEX,
        )
        self.assertEqual(response, '{"text":"complex"}')
        self.assertEqual(nim.models, ["moonshotai/kimi-k3"])
        await manager.close()

    async def test_failed_complex_model_falls_back(self) -> None:
        nim = FakeProvider(fail=True)
        fallback = FakeProvider(response='{"text":"fallback"}')
        manager = LLMManager(
            nim,
            "nvidia_nim",
            "moonshotai/kimi-k3",
            providers={"nvidia_nim": nim, "openrouter": fallback},
            routes={
                RoutingTier.COMPLEX: ModelTarget(
                    "nvidia_nim",
                    "moonshotai/kimi-k3",
                )
            },
            fallback_targets=(
                ModelTarget("openrouter", "openai/gpt-4o-mini"),
            ),
        )
        response = await manager.chat(
            [ChatMessage("user", "analisis")],
            tier=RoutingTier.COMPLEX,
        )
        self.assertEqual(response, '{"text":"fallback"}')
        self.assertEqual(fallback.models, ["openai/gpt-4o-mini"])
        await manager.close()

    async def test_openrouter_receives_prefill_and_cache_key(self) -> None:
        provider = AdvancedProvider()
        manager = LLMManager(provider, "openrouter", "model")
        await manager.chat(
            [ChatMessage("user", "halo")],
            tier=RoutingTier.FAST,
            json_prefill=True,
            cache_key="sena:discord_text:1:2",
        )
        self.assertEqual(provider.options["assistant_prefill"], "{")
        self.assertEqual(provider.options["cache_key"], "sena:discord_text:1:2")
        self.assertIs(provider.options["json_object"], True)
        await manager.close()


class NvidiaKimiConfigurationTests(unittest.TestCase):
    def test_kimi_keeps_reasoning_enabled_and_uses_json_mode(self) -> None:
        provider = NvidiaNimProvider(
            api_key="test",
            base_url="https://example.com/v1",
            request_timeout_seconds=10.0,
            max_tokens=300,
            retry_count=0,
            retry_delay_seconds=0.0,
        )
        body = provider._request_extra_body("moonshotai/kimi-k3", True)
        self.assertEqual(body["reasoning_effort"], "max")
        self.assertEqual(body["temperature"], 1.0)
        self.assertEqual(body["max_tokens"], 4096)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertNotIn("chat_template_kwargs", body)


if __name__ == "__main__":
    unittest.main()
