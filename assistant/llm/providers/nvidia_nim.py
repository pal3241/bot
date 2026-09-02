from assistant.llm.providers.openai_compatible import OpenAICompatibleProvider


class NvidiaNimProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        request_timeout_seconds: float,
        retry_count: int,
        retry_delay_seconds: float,
    ) -> None:
        super().__init__(
            provider_name="nvidia_nim",
            endpoint=f"{base_url.rstrip('/')}/chat/completions",
            api_key=api_key,
            request_timeout_seconds=request_timeout_seconds,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            extra_headers={},
        )
