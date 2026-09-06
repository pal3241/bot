import os
import unittest
from unittest.mock import patch

from assistant.llm.providers.nvidia_nim import NvidiaNimProvider


class NvidiaKimiLatencyTests(unittest.TestCase):
    def _provider(self) -> NvidiaNimProvider:
        return NvidiaNimProvider(
            api_key="test-key",
            base_url="https://example.test/v1",
            request_timeout_seconds=60.0,
            max_tokens=400,
            retry_count=2,
            retry_delay_seconds=1.0,
        )

    def test_kimi_defaults_use_high_reasoning_and_2048_token_floor(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SENA_KIMI_REASONING_EFFORT", None)
            os.environ.pop("SENA_KIMI_MIN_MAX_TOKENS", None)
            body = self._provider()._request_extra_body("moonshotai/kimi-k3", True)

        self.assertEqual(body["reasoning_effort"], "high")
        self.assertEqual(body["max_tokens"], 2048)
        self.assertEqual(body["response_format"], {"type": "json_object"})

    def test_kimi_latency_controls_are_configurable(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SENA_KIMI_REASONING_EFFORT": "medium",
                "SENA_KIMI_MIN_MAX_TOKENS": "1024",
            },
            clear=False,
        ):
            body = self._provider()._request_extra_body("moonshotai/kimi-k3", False)

        self.assertEqual(body["reasoning_effort"], "medium")
        self.assertEqual(body["max_tokens"], 1024)


if __name__ == "__main__":
    unittest.main()
