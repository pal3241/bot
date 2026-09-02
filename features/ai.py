import os
from dataclasses import replace

from assistant.manager import AssistantManager
from assistant.personality import (
    ALLOWED_VALUES,
    PersonalityBehavior,
    PersonalityConfig,
    PersonalityIdentity,
    PersonalityLanguage,
    PersonalityStyle,
)
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


async def _set_nvidia_url(manager: AssistantManager) -> None:
    base_url: str = (await ainput("NVIDIA NIM base URL: ")).strip()
    await _apply(manager, replace(manager.settings, nvidia_nim_base_url=base_url))


def _show_status(manager: AssistantManager) -> None:
    settings: AISettings = manager.settings
    personality: PersonalityConfig = manager.personality.config
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
    print(f"Personality       : {personality.name}")
    print(f"Archetype         : {personality.personality.archetype}")
    print(f"Dominance         : {personality.personality.dominance}/10")
    print(f"Roughness         : {personality.roughness_rules.level}/10")
    print(f"Tone              : {personality.style.tone}")
    print(f"Response length   : {personality.style.response_length}")
    print(f"Emoji usage       : {personality.style.emoji_usage}")
    print(f"Language mode     : {personality.language.mode}")
    print(f"Default language  : {personality.language.default_language}")
    print(f"OpenRouter key    : {_api_key_status('OPENROUTER_API_KEY')}")
    print(f"NVIDIA NIM key    : {_api_key_status('NVIDIA_NIM_API_KEY')}")


async def _controlled_value(label: str, values: frozenset[str]) -> str:
    choices: list[str] = sorted(values)
    print(f"\n{label.upper()}")
    for number, value in enumerate(choices, start=1):
        print(f"{number}. {value}")
    raw: str = (await ainput(f"Pilih {label}: ")).strip()
    try:
        index: int = int(raw) - 1
    except ValueError as error:
        raise ValueError(f"Pilihan {label} harus berupa nomor.") from error
    if not 0 <= index < len(choices):
        raise ValueError(f"Pilihan {label} tidak tersedia.")
    return choices[index]


async def _personality_menu(manager: AssistantManager) -> None:
    while True:
        config: PersonalityConfig = manager.personality.config
        style: PersonalityStyle = config.style
        language: PersonalityLanguage = config.language
        behavior: PersonalityBehavior = config.behavior
        print("\n" + "=" * 55)
        print("              PERSONALITY SETTINGS")
        print("=" * 55)
        print(f"Nama       : {config.name}")
        print(f"Tone       : {style.tone}")
        print(f"Energy     : {style.energy}")
        print(f"Humor      : {style.humor}")
        print(f"Friendship : {style.friendliness}")
        print(f"Formality  : {style.formality}")
        print(f"Length     : {style.response_length}")
        print(f"Emoji      : {style.emoji_usage}")
        print(f"Archetype  : {config.personality.archetype}")
        print(f"Language   : {language.mode} (default={language.default_language})")
        print("\n1. Nama")
        print("2. Deskripsi")
        print("3. Role")
        print("4. Tone")
        print("5. Energy")
        print("6. Humor")
        print("7. Friendliness")
        print("8. Formality")
        print("9. Response length")
        print("10. Emoji usage")
        print("11. Language mode")
        print("12. Default language")
        print("13. Follow user language ON/OFF")
        print("14. Direct ON/OFF")
        print("15. Protective ON/OFF")
        print("16. Slightly rude ON/OFF")
        print("17. Playful teasing ON/OFF")
        print("18. Likes to correct user ON/OFF")
        print("19. Reload config dari file")
        print("\nexit = kembali")
        choice: str = (await ainput("\nPilih: ")).strip().lower()
        updated: PersonalityConfig | None = None
        if choice == "1":
            name: str = (await ainput("Nama personality: ")).strip()
            updated = replace(config, name=name)
        elif choice == "2":
            description: str = (await ainput("Deskripsi: ")).strip()
            identity: PersonalityIdentity = replace(
                config.identity, description=description
            )
            updated = replace(config, identity=identity)
        elif choice == "3":
            role: str = (await ainput("Role: ")).strip()
            updated = replace(config, identity=replace(config.identity, role=role))
        elif choice in {"4", "5", "6", "7", "8", "9", "10"}:
            field_by_choice: dict[str, str] = {
                "4": "tone",
                "5": "energy",
                "6": "humor",
                "7": "friendliness",
                "8": "formality",
                "9": "response_length",
                "10": "emoji_usage",
            }
            field: str = field_by_choice[choice]
            value: str = await _controlled_value(field, ALLOWED_VALUES[field])
            updated = replace(config, style=replace(style, **{field: value}))
        elif choice == "11":
            mode: str = await _controlled_value(
                "language mode", ALLOWED_VALUES["language.mode"]
            )
            updated = replace(config, language=replace(language, mode=mode))
        elif choice == "12":
            default_language: str = (await ainput("Kode bahasa default: ")).strip()
            updated = replace(
                config,
                language=replace(language, default_language=default_language),
            )
        elif choice == "13":
            updated = replace(
                config,
                language=replace(
                    language,
                    follow_user_language=not language.follow_user_language,
                ),
            )
        elif choice in {"14", "15", "16", "17", "18"}:
            behavior_field_by_choice: dict[str, str] = {
                "14": "direct",
                "15": "protective",
                "16": "slightly_rude",
                "17": "playful_teasing",
                "18": "likes_to_correct_user",
            }
            behavior_field: str = behavior_field_by_choice[choice]
            current: bool = getattr(behavior, behavior_field)
            updated = replace(
                config,
                behavior=replace(behavior, **{behavior_field: not current}),
            )
        elif choice == "19":
            manager.personality.reload()
            print("Personality berhasil dimuat ulang dari file.")
        elif choice == "exit":
            return
        else:
            print("Pilihan tidak tersedia.")
        if updated is not None:
            manager.personality.update(updated)
            print("Personality diterapkan dan disimpan.")


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
        print(f"Personality: {manager.personality.config.name}")
        print("\n1. Ganti provider")
        print("2. Ganti model provider aktif")
        print("3. Atur maks token")
        print("4. Atur request timeout")
        print("5. Atur jumlah retry")
        print("6. Atur retry delay")
        print("7. Atur session timeout")
        print("8. Atur batas history")
        print("9. Personality Settings")
        print("10. Atur NVIDIA NIM base URL")
        print("11. Reload personality")
        print("12. Hapus semua session AI")
        print("13. Lihat status lengkap")
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
            await _personality_menu(manager)
        elif choice == "10":
            await _set_nvidia_url(manager)
        elif choice == "11":
            manager.personality.reload()
            print("Personality berhasil dimuat ulang.")
        elif choice == "12":
            manager.sessions.clear()
            print("Semua session dan history AI telah dihapus.")
        elif choice == "13":
            _show_status(manager)
        elif choice == "exit":
            return
        else:
            print("Pilihan tidak tersedia.")
