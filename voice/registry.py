from collections.abc import Callable

from voice.providers.base import TTSProvider
from voice.providers.gtts_provider import GTTSProvider


ProviderFactory = Callable[[], TTSProvider]
PROVIDERS: dict[str, ProviderFactory] = {"gtts": GTTSProvider}


def create_provider(name: str) -> TTSProvider:
    normalized_name: str = name.strip().lower()
    provider_factory: ProviderFactory | None = PROVIDERS.get(normalized_name)
    if provider_factory is None:
        tersedia: str = ", ".join(PROVIDERS)
        raise ValueError(
            f"TTS provider tidak ditemukan: '{name}'. Provider tersedia: {tersedia}."
        )
    return provider_factory()


def register_provider(name: str, provider_factory: ProviderFactory) -> None:
    normalized_name: str = name.strip().lower()
    if not normalized_name:
        raise ValueError("Nama TTS provider tidak boleh kosong.")
    if normalized_name in PROVIDERS:
        raise ValueError(f"TTS provider '{normalized_name}' sudah terdaftar.")
    PROVIDERS[normalized_name] = provider_factory

