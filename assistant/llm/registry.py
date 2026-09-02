import os
from collections.abc import Callable

from assistant.llm.base import LLMConfigurationError, LLMProvider
from assistant.llm.providers import NvidiaNimProvider, OpenRouterProvider


ProviderFactory = Callable[[], LLMProvider]


def require_environment(name: str) -> str:
    value: str | None = os.getenv(name)
    if value is None or not value.strip():
        raise LLMConfigurationError(
            f"{name} tidak ditemukan atau kosong di file .env untuk provider aktif."
        )
    return value.strip()


def create_provider(
    name: str,
    nvidia_base_url: str,
    request_timeout_seconds: float,
    max_tokens: int,
    retry_count: int,
    retry_delay_seconds: float,
) -> LLMProvider:
    factories: dict[str, ProviderFactory] = {
        "openrouter": lambda: OpenRouterProvider(
            api_key=require_environment("OPENROUTER_API_KEY"),
            request_timeout_seconds=request_timeout_seconds,
            max_tokens=max_tokens,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
        ),
        "nvidia_nim": lambda: NvidiaNimProvider(
            api_key=require_environment("NVIDIA_NIM_API_KEY"),
            base_url=nvidia_base_url,
            request_timeout_seconds=request_timeout_seconds,
            max_tokens=max_tokens,
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
        ),
    }
    factory: ProviderFactory | None = factories.get(name)
    if factory is None:
        raise LLMConfigurationError(
            f"LLM_PROVIDER '{name}' tidak tersedia. Pilih: {', '.join(factories)}."
        )
    return factory()
