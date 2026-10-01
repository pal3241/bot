import os
import unittest
from unittest.mock import patch

from assistant.llm.providers.nvidia_nim import NvidiaNimProvider


class NvidiaGlmLatencyTests(unittest.TestCase):
    def _provider(self) -> NvidiaNimProvider:
        return NvidiaNimProvider(
            api_key="test-key",
            base_url="https://example.test/v1",
            request_timeout_seconds=60.0,
            max_tokens=400,
            retry_count=2,
            retry_delay_seconds=1.0,
        )

    def test_glm_defaults_use_high_reasoning_and_1024_token_floor(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SENA_GLM_REASONING_EFFORT", None)
            os.environ.pop("SENA_GLM_MIN_MAX_TOKENS", None)
            body = self._provider()._request_extra_body(
                "z-ai/glm-5-3-flash", True
            )

        self.assertEqual(body["reasoning_effort"], "high")
        self.assertEqual(body["max_tokens"], 1024)
        self.assertEqual(body["chat_template_kwargs"], {"clear_thinking": True})
        self.assertEqual(body["response_format"], {"type": "json_object"})

    def test_glm_reasoning_controls_are_configurable(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SENA_GLM_REASONING_EFFORT": "max",
                "SENA_GLM_MIN_MAX_TOKENS": "1536",
            },
            clear=False,
        ):
            body = self._provider()._request_extra_body(
                "z-ai/glm-5-3-flash", False
            )

        self.assertEqual(body["reasoning_effort"], "max")
        self.assertEqual(body["max_tokens"], 1536)


if __name__ == "__main__":
    unittest.main()
