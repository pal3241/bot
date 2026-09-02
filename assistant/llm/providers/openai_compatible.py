import asyncio
import json
from time import monotonic

import aiohttp

from assistant.llm.base import (
    ChatMessage,
    LLMConfigurationError,
    LLMProvider,
    LLMProviderError,
)


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        provider_name: str,
        endpoint: str,
        api_key: str,
        request_timeout_seconds: float,
        retry_count: int,
        retry_delay_seconds: float,
        extra_headers: dict[str, str],
    ) -> None:
        if not api_key.strip():
            raise LLMConfigurationError(
                f"API key provider '{provider_name}' tidak tersedia di file .env."
            )
        self._provider_name: str = provider_name
        self._endpoint: str = endpoint
        self._api_key: str = api_key
        self._timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(
            total=request_timeout_seconds
        )
        self._retry_count: int = retry_count
        self._retry_delay_seconds: float = retry_delay_seconds
        self._extra_headers: dict[str, str] = dict(extra_headers)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    def _parse_response(self, body: str, status: int) -> str:
        try:
            payload: object = json.loads(body)
        except json.JSONDecodeError as error:
            raise LLMProviderError(
                f"{self._provider_name} mengembalikan JSON tidak valid: status={status}, body={body[:1000]}"
            ) from error
        if not isinstance(payload, dict):
            raise LLMProviderError(
                f"{self._provider_name} mengembalikan root JSON bukan object: status={status}, body={body[:1000]}"
            )
        choices: object = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise LLMProviderError(
                f"{self._provider_name} tidak mengembalikan choices yang valid: status={status}, body={body[:1000]}"
            )
        message: object = choices[0].get("message")
        if not isinstance(message, dict):
            raise LLMProviderError(
                f"{self._provider_name} tidak mengembalikan message yang valid: status={status}, body={body[:1000]}"
            )
        content: object = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError(
                f"{self._provider_name} mengembalikan response AI kosong: status={status}, body={body[:1000]}"
            )
        return content.strip()

    async def chat(self, messages: list[ChatMessage], model: str) -> str:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }
        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "stream": False,
        }
        started: float = monotonic()
        print(f"[SENA] request started provider={self._provider_name} model={model}")
        last_error: Exception | None = None
        for attempt in range(1, self._retry_count + 2):
            try:
                session: aiohttp.ClientSession = await self._get_session()
                async with session.post(
                    self._endpoint, headers=headers, json=payload
                ) as response:
                    body: str = await response.text()
                    if response.status >= 400:
                        error = LLMProviderError(
                            f"{self._provider_name} POST {self._endpoint} gagal: "
                            f"status={response.status}, model={model}, body={body[:2000]}"
                        )
                        if response.status < 500 and response.status != 429:
                            raise error
                        last_error = error
                    else:
                        text: str = self._parse_response(body, response.status)
                        print(
                            f"[SENA] request completed provider={self._provider_name} "
                            f"latency={monotonic() - started:.3f}s response_chars={len(text)}"
                        )
                        return text
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                last_error = error
            if attempt <= self._retry_count:
                print(
                    f"[SENA] request retry provider={self._provider_name} attempt={attempt} "
                    f"error={type(last_error).__name__}: {last_error}"
                )
                await asyncio.sleep(self._retry_delay_seconds * attempt)
        raise LLMProviderError(
            f"{self._provider_name} gagal setelah {self._retry_count + 1} percobaan: {last_error}"
        ) from last_error

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
