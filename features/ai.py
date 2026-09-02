import os
from dataclasses import replace

from assistant.manager import AssistantManager
from assistant.settings import AISettings, save_settings
from config import AI_SETTINGS_FILE
from core.context import AppContext
from core.io import ainput
from core.registry import feature


def _api_key_status(name: str) -> str:
    value: str | None = os.getenv(name)
    return "tersedia" if value is not None and value.strip() else "belum tersedia"


def _active_model(settings: AISettings) -> str:
    if settings.provider_name == "openrouter":
        return settings.openrouter_model
    return settings.nvidia_nim_model


async def _apply(manager: AssistantManager, settings: AISettings) -> None:
    await manager.apply_settings(settings)
    save_settings(AI_SETTINGS_FILE, settings)
    print("Pengaturan AI diterapkan dan disimpan.")


async def _choose_provider(manager: AssistantManager) -> None:
    print("\n1. OpenRouter")
    print("2. NVIDIA NIM")
    choice: str = (await ainput("Pilih provider: ")).strip()
    provider_by_choice: dict[str, str] = {"1": "openrouter", "2": "nvidia_nim"}
    provider: str | None = provider_by_choice.get(choice)
    if provider is None:
        raise ValueError("Pilihan provider AI tidak valid.")
    await _apply(manager, replace(manager.settings, provider_name=provider))


async def _set_model(manager: AssistantManager) -> None:
    settings: AISettings = manager.settings
    model: str = (await ainput(f"Model {settings.provider_name}: ")).strip()
    if settings.provider_name == "openrouter":
        updated: AISettings = replace(settings, openrouter_model=model)
    else:
        updated = replace(settings, nvidia_nim_model=model)
    await _apply(manager, updated)


async def _set_positive_int(
    manager: AssistantManager, field_name: str, prompt: str
) -> None:
    value: int = int((await ainput(prompt)).strip())
    await _apply(manager, replace(manager.settings, **{field_name: value}))


async def _set_number(manager: AssistantManager, field_name: str, prompt: str) -> None:
    value: float = float((await ainput(prompt)).strip())
    await _apply(manager, replace(manager.settings, **{field_name: value}))


async def _set_language_mode(manager: AssistantManager) -> None:
    mode: str = (await ainput("Language mode (auto/fixed): ")).strip().lower()
    await _apply(manager, replace(manager.settings, language_mode=mode))


async def _set_language(manager: AssistantManager) -> None:
    language: str = (await ainput("Kode bahasa fixed, contoh id/en/ja: ")).strip()
    await _apply(manager, replace(manager.settings, language=language))


async def _set_nvidia_url(manager: AssistantManager) -> None:
    base_url: str = (await ainput("NVIDIA NIM base URL: ")).strip()
    await _apply(manager, replace(manager.settings, nvidia_nim_base_url=base_url))


def _show_status(manager: AssistantManager) -> None:
    settings: AISettings = manager.settings
    print("\n" + "=" * 55)
    print("                 AI STATUS")
    print("=" * 55)
    print(f"Provider          : {settings.provider_name}")
    print(f"Model aktif       : {_active_model(settings)}")
    print(f"Model OpenRouter  : {settings.openrouter_model}")
    print(f"Model NVIDIA NIM  : {settings.nvidia_nim_model}")
    print(f"NVIDIA base URL   : {settings.nvidia_nim_base_url}")
    print(f"Maks token        : {settings.max_tokens}")
    print(f"Request timeout   : {settings.request_timeout_seconds:.1f} detik")
    print(f"Retry             : {settings.retry_count}")
    print(f"Retry delay       : {settings.retry_delay_seconds:.1f} detik")
    print(f"Session timeout   : {settings.chat_timeout_seconds:.1f} detik")
    print(f"History maksimal  : {settings.history_max_messages} message")
    print(f"Language mode     : {settings.language_mode}")
    print(f"Fixed language    : {settings.language}")
    print(f"Personality       : {manager.personality.load()[:40]}...")
    print(f"OpenRouter key    : {_api_key_status('OPENROUTER_API_KEY')}")
    print(f"NVIDIA NIM key    : {_api_key_status('NVIDIA_NIM_API_KEY')}")


@feature("AI Settings")
async def ai_settings_feature(ctx: AppContext) -> None:
    manager: AssistantManager = ctx.assistant
    while True:
        settings: AISettings = manager.settings
        print("\n" + "=" * 55)
        print("                 AI SETTINGS")
        print("=" * 55)
        print(f"Provider : {settings.provider_name}")
        print(f"Model    : {_active_model(settings)}")
        print(f"Token    : {settings.max_tokens}")
        print(f"Language : {settings.language_mode}")
        print("\n1. Ganti provider")
        print("2. Ganti model provider aktif")
        print("3. Atur maks token")
        print("4. Atur request timeout")
        print("5. Atur jumlah retry")
        print("6. Atur retry delay")
        print("7. Atur session timeout")
        print("8. Atur batas history")
        print("9. Atur language mode")
        print("10. Atur fixed language")
        print("11. Atur NVIDIA NIM base URL")
        print("12. Reload personality")
        print("13. Hapus semua session AI")
        print("14. Lihat status lengkap")
        print("\nexit = kembali")
        choice: str = (await ainput("\nPilih: ")).strip().lower()
        if choice == "1":
            await _choose_provider(manager)
        elif choice == "2":
            await _set_model(manager)
        elif choice == "3":
            await _set_positive_int(manager, "max_tokens", "Maks token: ")
        elif choice == "4":
            await _set_number(manager, "request_timeout_seconds", "Timeout detik: ")
        elif choice == "5":
            await _set_positive_int(manager, "retry_count", "Jumlah retry: ")
        elif choice == "6":
            await _set_number(manager, "retry_delay_seconds", "Retry delay detik: ")
        elif choice == "7":
            await _set_number(manager, "chat_timeout_seconds", "Session timeout detik: ")
        elif choice == "8":
            await _set_positive_int(manager, "history_max_messages", "Maks history: ")
        elif choice == "9":
            await _set_language_mode(manager)
        elif choice == "10":
            await _set_language(manager)
        elif choice == "11":
            await _set_nvidia_url(manager)
        elif choice == "12":
            manager.personality.reload()
            print("Personality berhasil dimuat ulang.")
        elif choice == "13":
            manager.sessions.clear()
            print("Semua session dan history AI telah dihapus.")
        elif choice == "14":
            _show_status(manager)
        elif choice == "exit":
            return
        else:
            print("Pilihan tidak tersedia.")
