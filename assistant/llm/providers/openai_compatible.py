import asyncio
import json
import time
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
        self._provider_name = provider_name
        self._endpoint = endpoint
        self._api_key = api_key
        self._timeout = aiohttp.ClientTimeout(
            total=request_timeout_seconds,
            connect=min(10.0, request_timeout_seconds),
            sock_connect=min(10.0, request_timeout_seconds),
        )
        self._max_tokens = max_tokens
        self._retry_count = retry_count
        self._retry_delay_seconds = retry_delay_seconds
        self._extra_headers = dict(extra_headers)
        self._extra_body = dict(extra_body)
        self._session: aiohttp.ClientSession | None = None
        self._last_latency_ms: float | None = None
        self._last_error: str | None = None
        self._last_attempt_at: float | None = None
        self._last_success_at: float | None = None
        self._consecutive_failures = 0

    def runtime_health(self) -> dict[str, object]:
        return {
            "latency_ms": self._last_latency_ms,
            "last_error": self._last_error,
            "last_attempt_at": self._last_attempt_at,
            "last_success_at": self._last_success_at,
            "consecutive_failures": self._consecutive_failures,
        }

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

    def _request_extra_body(self, model: str, json_object: bool) -> dict[str, object]:
        del model
        body = dict(self._extra_body)
        if json_object:
            body["response_format"] = {"type": "json_object"}
        return body

    def _parse_response(
        self,
        body: str,
        status: int,
        assistant_prefill: str | None,
    ) -> str:
        try:
            payload: object = json.loads(body)
        except json.JSONDecodeError as error:
            raise LLMProviderError(
                f"{self._provider_name} mengembalikan JSON tidak valid: "
                f"status={status}, body={body[:1000]}"
            ) from error
        if not isinstance(payload, dict):
            raise LLMProviderError(
                f"{self._provider_name} mengembalikan root JSON bukan object: "
                f"status={status}, body={body[:1000]}"
            )
        choices: object = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise LLMProviderError(
                f"{self._provider_name} tidak mengembalikan choices yang valid: "
                f"status={status}, body={body[:1000]}"
            )
        message: object = choices[0].get("message")
        if not isinstance(message, dict):
            raise LLMProviderError(
                f"{self._provider_name} tidak mengembalikan message yang valid: "
                f"status={status}, body={body[:1000]}"
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
                f"{self._provider_name} mengembalikan response AI kosong: "
                f"status={status}, body={body[:1000]}"
            )

        result = content.strip()
        if assistant_prefill and not result.startswith(assistant_prefill):
            result = assistant_prefill + result

        usage = payload.get("usage")
        if isinstance(usage, dict):
            details = usage.get("prompt_tokens_details")
            if isinstance(details, dict):
                cached = details.get("cached_tokens", 0)
                written = details.get("cache_write_tokens", 0)
                print(
                    f"[SENA CACHE] provider={self._provider_name} "
                    f"cached_tokens={cached} cache_write_tokens={written}"
                )
        return result

    async def chat(self, messages: list[ChatMessage], model: str) -> str:
        return await self.chat_with_options(messages, model)

    async def chat_with_options(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        assistant_prefill: str | None = None,
        cache_key: str | None = None,
        json_object: bool = False,
    ) -> str:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self._extra_headers,
        }
        request_messages = [
            {"role": message.role, "content": message.content} for message in messages
        ]
        if assistant_prefill:
            request_messages.append(
                {"role": "assistant", "content": assistant_prefill}
            )

        payload: dict[str, object] = {
            "model": model,
            "messages": request_messages,
            "stream": False,
            "max_tokens": self._max_tokens,
            **self._request_extra_body(model, json_object),
        }
        if cache_key and self._provider_name == "openrouter":
            payload["session_id"] = cache_key[:256]

        started = monotonic()
        self._last_attempt_at = time.time()
        print(
            f"[SENA] request started provider={self._provider_name} model={model} "
            f"prefill={'on' if assistant_prefill else 'off'} "
            f"cache_key={'on' if cache_key else 'off'}"
        )
        last_error: Exception | None = None
        for attempt in range(1, self._retry_count + 2):
            attempt_started = monotonic()
            try:
                session = await self._get_session()
                async with session.post(
                    self._endpoint, headers=headers, json=payload
                ) as response:
                    headers_received = monotonic()
                    body = await response.text()
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
                        text = self._parse_response(
                            body,
                            response.status,
                            assistant_prefill,
                        )
                        print(
                            f"[SENA] request completed provider={self._provider_name} "
                            f"latency={monotonic() - started:.3f}s "
                            f"ttfb={ttfb_seconds:.3f}s body={body_seconds:.3f}s "
                            f"response_chars={len(text)}"
                        )
                        self._last_latency_ms = (monotonic() - started) * 1000.0
                        self._last_error = None
                        self._last_success_at = time.time()
                        self._consecutive_failures = 0
                        return text
            except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                last_error = error
            if attempt <= self._retry_count:
                print(
                    f"[SENA] request retry provider={self._provider_name} "
                    f"attempt={attempt} error={type(last_error).__name__}: {last_error}"
                )
                await asyncio.sleep(self._retry_delay_seconds * attempt)
        self._last_error = f"{type(last_error).__name__}: {last_error}"
        self._consecutive_failures += 1
        raise LLMProviderError(
            f"{self._provider_name} gagal setelah "
            f"{self._retry_count + 1} percobaan: {last_error}"
        ) from last_error

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
