import os

from assistant.llm.providers.openai_compatible import OpenAICompatibleProvider


def _positive_int_env(name: str, fallback: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        value = int(raw)
    except ValueError:
        return fallback
    return value if value > 0 else fallback


def _kimi_reasoning_effort() -> str:
    value = os.getenv("SENA_KIMI_REASONING_EFFORT", "high").strip().casefold()
    return value if value in {"low", "medium", "high", "max"} else "high"


class NvidiaNimProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        request_timeout_seconds: float,
        max_tokens: int,
        retry_count: int,
        retry_delay_seconds: float,
    ) -> None:
        super().__init__(
            provider_name="nvidia_nim",
            endpoint=f"{base_url.rstrip('/')}/chat/completions",
            api_key=api_key,
            request_timeout_seconds=request_timeout_seconds,
            max_tokens=max_tokens,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            extra_headers={},
            extra_body={},
        )

    def _request_extra_body(self, model: str, json_object: bool) -> dict[str, object]:
        normalized = model.strip().casefold()
        if normalized == "moonshotai/kimi-k3":
            body: dict[str, object] = {
                "temperature": 1.0,
                "reasoning_effort": _kimi_reasoning_effort(),
                # Kimi K3 needs room for reasoning, but forcing 4096 tokens plus
                # max reasoning made compact math questions unnecessarily slow.
                "max_tokens": max(
                    self._max_tokens,
                    _positive_int_env("SENA_KIMI_MIN_MAX_TOKENS", 2048),
                ),
            }
            if json_object:
                body["response_format"] = {"type": "json_object"}
            return body

        body = {"chat_template_kwargs": {"enable_thinking": False}}
        if json_object:
            body["response_format"] = {"type": "json_object"}
        return body
