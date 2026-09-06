import json
import unittest

from assistant.llm.base import LLMProviderError
from assistant.llm.providers.openai_compatible import OpenAICompatibleProvider


def provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        provider_name="openrouter",
        endpoint="https://example.invalid/chat/completions",
        api_key="test",
        request_timeout_seconds=5.0,
        max_tokens=300,
        retry_count=0,
        retry_delay_seconds=0.0,
        extra_headers={},
        extra_body={},
    )


class OpenAICompatibleResponseTests(unittest.TestCase):
    def test_accepts_structured_final_json_from_reasoning_when_content_is_null(self) -> None:
        structured = {
            "text": "Hai, boss juga 😘",
            "memory": None,
            "expression": {
                "emotion": "affectionate",
                "intent": "greeting",
                "intensity": 0.7,
                "bonus_media": "none",
                "allow_bonus": False,
            },
            "actions": [],
        }
        body = json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": None,
                            "reasoning": json.dumps(structured),
                        },
                    }
                ]
            }
        )
        parsed = provider()._parse_response(body, 200, None)
        self.assertEqual(json.loads(parsed), structured)

    def test_does_not_expose_arbitrary_reasoning_as_final_content(self) -> None:
        body = json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": None,
                            "reasoning": "I should reason privately before answering.",
                        },
                    }
                ]
            }
        )
        with self.assertRaises(LLMProviderError):
            provider()._parse_response(body, 200, None)


if __name__ == "__main__":
    unittest.main()
