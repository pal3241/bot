from assistant.llm.providers.openai_compatible import OpenAICompatibleProvider


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
                "reasoning_effort": "max",
            }
            if json_object:
                body["response_format"] = {"type": "json_object"}
            return body

        body = {"chat_template_kwargs": {"enable_thinking": False}}
        if json_object:
            body["response_format"] = {"type": "json_object"}
        return body
