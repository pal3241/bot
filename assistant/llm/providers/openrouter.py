from assistant.llm.providers.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        api_key: str,
        request_timeout_seconds: float,
        max_tokens: int,
        retry_count: int,
        retry_delay_seconds: float,
    ) -> None:
        super().__init__(
            provider_name="openrouter",
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            api_key=api_key,
            request_timeout_seconds=request_timeout_seconds,
            max_tokens=max_tokens,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            extra_headers={"X-Title": "Sena Discord Assistant"},
            extra_body={},
        )
