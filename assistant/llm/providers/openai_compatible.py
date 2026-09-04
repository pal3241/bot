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
        max_tokens: int,
        retry_count: int,
        retry_delay_seconds: float,
        extra_headers: dict[str, str],
        extra_body: dict[str, object],
    ) -> None:
        if not api_key.strip():
            raise LLMConfigurationError(
                f"API key provider '{provider_name}' tidak tersedia di file .env."
            )
        if max_tokens <= 0:
            raise LLMConfigurationError("LLM_MAX_TOKENS harus lebih besar dari nol.")
        self._provider_name: str = provider_name
        self._endpoint: str = endpoint
        self._api_key: str = api_key
        self._timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(
            total=request_timeout_seconds,
            connect=min(10.0, request_timeout_seconds),
            sock_connect=min(10.0, request_timeout_seconds),
        )
        self._max_tokens: int = max_tokens
        self._retry_count: int = retry_count
        self._retry_delay_seconds: float = retry_delay_seconds
        self._extra_headers: dict[str, str] = dict(extra_headers)
        self._extra_body: dict[str, object] = dict(extra_body)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=16,
                limit_per_host=8,
                ttl_dns_cache=300,
                keepalive_timeout=45.0,
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                connector=connector,
            )
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
        finish_reason: object = choices[0].get("finish_reason")
        if finish_reason == "length":
            raise LLMProviderError(
                f"{self._provider_name} memotong response karena batas max_tokens="
                f"{self._max_tokens}. Naikkan nilai maks token melalui AI Settings."
            )
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError(
                f"{self._provider_name} mengembalikan response AI kosong: status={status}, body={body[:1000]}"
            )
        return content.strip()

    async def chat(self, messages: list[ChatMessage], model: str) -> str:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self._extra_headers,
        }
        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "stream": False,
            "max_tokens": self._max_tokens,
            **self._extra_body,
        }
        started: float = monotonic()
        print(f"[SENA] request started provider={self._provider_name} model={model}")
        last_error: Exception | None = None
        for attempt in range(1, self._retry_count + 2):
            attempt_started = monotonic()
            try:
                session: aiohttp.ClientSession = await self._get_session()
                async with session.post(
                    self._endpoint, headers=headers, json=payload
                ) as response:
                    headers_received = monotonic()
                    body: str = await response.text()
                    body_received = monotonic()
                    ttfb_seconds = headers_received - attempt_started
                    body_seconds = body_received - headers_received
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
                            f"latency={monotonic() - started:.3f}s "
                            f"ttfb={ttfb_seconds:.3f}s body={body_seconds:.3f}s "
                            f"response_chars={len(text)}"
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