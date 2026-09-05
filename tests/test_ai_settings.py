import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from assistant.settings import AISettings, load_settings, save_settings, validate_settings


def settings() -> AISettings:
    return AISettings(
        provider_name="openrouter",
        openrouter_model="openai/gpt-4o-mini",
        nvidia_nim_model="nvidia/nemotron-3.5-lightning-30b-a3b",
        nvidia_nim_base_url="https://integrate.api.nvidia.com/v1",
        max_tokens=300,
        request_timeout_seconds=60.0,
        retry_count=2,
        retry_delay_seconds=1.0,
        chat_timeout_seconds=120.0,
        history_max_messages=20,
    )


class AISettingsTests(unittest.TestCase):
    def test_routing_settings_round_trip(self) -> None:
        expected = replace(
            settings(),
            fast_provider="nvidia_nim",
            fast_model="meta/llama-3.1-8b-instruct",
            standard_provider="openrouter",
            standard_model="qwen/qwen3-30b-a3b",
            complex_provider="nvidia_nim",
            complex_model="moonshotai/kimi-k3",
            prompt_cache_enabled=False,
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ai_settings.json"
            save_settings(path, expected)
            self.assertEqual(load_settings(path, settings()), expected)

    def test_legacy_file_gets_new_routing_defaults(self) -> None:
        initial = settings()
        legacy = {
            "provider_name": initial.provider_name,
            "openrouter_model": initial.openrouter_model,
            "nvidia_nim_model": initial.nvidia_nim_model,
            "nvidia_nim_base_url": initial.nvidia_nim_base_url,
            "max_tokens": initial.max_tokens,
            "request_timeout_seconds": initial.request_timeout_seconds,
            "retry_count": initial.retry_count,
            "retry_delay_seconds": initial.retry_delay_seconds,
            "chat_timeout_seconds": initial.chat_timeout_seconds,
            "history_max_messages": initial.history_max_messages,
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ai_settings.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            loaded = load_settings(path, initial)
        self.assertTrue(loaded.routing_enabled)
        self.assertEqual(loaded.fast_provider, "primary")
        self.assertEqual(loaded.complex_model, "moonshotai/kimi-k3")

    def test_explicit_provider_requires_model(self) -> None:
        invalid = replace(settings(), fast_provider="nvidia_nim", fast_model="")
        with self.assertRaisesRegex(ValueError, "Model route FAST"):
            validate_settings(invalid)


if __name__ == "__main__":
    unittest.main()
