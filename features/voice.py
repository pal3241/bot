from dataclasses import replace
from pathlib import Path

import discord
from discord.ext import voice_recv

from config import RVC_MODELS_FOLDER, STT_SETTINGS_FILE
from core.context import AppContext
from core.io import ainput, pilih_server
from core.registry import feature
from voice.manager import VoiceManager
from voice.models import RVCModel, delete_model, get_model, import_model, list_models
from voice.queue import TTSQueue
from voice.registry import PROVIDERS
from voice.converters.registry import CONVERTERS
from voice.converters.rvc_converter import RVCConverter
from voice.converters.settings import (
    VoiceConverterSettings,
    set_converter,
    set_enabled,
    set_index_ratio,
    set_model,
    set_pitch,
    set_protect,
)
from voice.converters.w_okada_client import WOkadaModel
from stt.models import STTResult
from stt.service import STTService
from stt.settings import STTSettings, load_configured_settings


async def pilih_voice_channel(ctx: AppContext) -> discord.VoiceChannel | None:
    if ctx.guild is None and await pilih_server(ctx) is None:
        return None
    guild: discord.Guild = ctx.guild
    channels: list[discord.VoiceChannel] = list(guild.voice_channels)
    if not channels:
        print("\nServer tidak memiliki voice channel.")
        return None

    print("\n" + "=" * 50)
    print(f"VOICE CHANNEL - {guild.name}")
    print("=" * 50)
    for nomor, channel in enumerate(channels, start=1):
        print(f"{nomor}. {channel.name} ({len(channel.members)} anggota)")
    print("\nKetik exit untuk batal.")

    while True:
        pilihan: str = (await ainput("\nPilih voice channel: ")).strip()
        if pilihan.lower() == "exit":
            return None
        try:
            index: int = int(pilihan) - 1
        except ValueError:
            print("Pilihan tidak valid.")
            continue
        if 0 <= index < len(channels):
            ctx.voice_channel = channels[index]
            print(f"\nVoice channel aktif: {ctx.voice_channel.name}")
            return ctx.voice_channel
        print("Pilihan tidak valid.")


async def join_voice_channel(ctx: AppContext) -> voice_recv.VoiceRecvClient | None:
    if ctx.voice_channel is None and await pilih_voice_channel(ctx) is None:
        return None
    channel: discord.VoiceChannel = ctx.voice_channel
    existing_client: discord.VoiceClient | None = channel.guild.voice_client

    try:
        if existing_client is not None and existing_client.is_connected():
            if not isinstance(existing_client, voice_recv.VoiceRecvClient):
                raise RuntimeError(
                    "Voice connection lama tidak mendukung receive. Disconnect lalu join ulang."
                )
            if existing_client.channel.id != channel.id:
                await existing_client.move_to(channel)
            print(f"Bot terhubung ke VC: {channel.name}")
            return existing_client
        voice_client: voice_recv.VoiceRecvClient = await channel.connect(
            cls=voice_recv.VoiceRecvClient
        )
    except discord.Forbidden as error:
        raise PermissionError(
            f"Bot tidak memiliki izin Connect/Speak di voice channel '{channel.name}'."
        ) from error
    except discord.ClientException as error:
        raise RuntimeError(f"Gagal bergabung ke voice channel '{channel.name}': {error}") from error

    print(f"Bot terhubung ke VC: {channel.name}")
    return voice_client


async def terminal_tts(ctx: AppContext, manager: VoiceManager) -> None:
    voice_client: discord.VoiceClient | None = await join_voice_channel(ctx)
    if voice_client is None:
        return

    queue: TTSQueue = TTSQueue(manager, voice_client)
    queue.start()
    print("\nKetik teks yang ingin dimasukkan ke TTS queue.")
    print("Anda dapat terus mengetik selama bot berbicara.")
    print("Ketik status untuk melihat queue atau clear untuk menghapus yang belum diproses.")
    print("Ketik exit untuk menunggu antrean selesai dan kembali.\n")
    try:
        while True:
            queue.raise_worker_error()
            text: str = await ainput("TTS > ")
            if text.strip().lower() == "exit":
                print("Menunggu TTS queue selesai...")
                await queue.finish()
                return
            if text.strip().lower() == "status":
                print(f"QUEUE > pending={queue.pending_count}")
                continue
            if text.strip().lower() == "clear":
                removed: int = await queue.clear_pending()
                print(f"QUEUE > {removed} item belum diproses dihapus")
                continue
            if not text.strip():
                print("Teks kosong tidak diproses.")
                continue
            posisi: int = await queue.enqueue(text)
            print(f"QUEUE > ditambahkan, menunggu={posisi}")
    finally:
        if not queue.is_finished:
            await queue.finish()


async def pilih_provider(manager: VoiceManager) -> None:
    names: list[str] = list(PROVIDERS)
    print("\n" + "=" * 40)
    print("TTS PROVIDERS")
    print("=" * 40)
    for nomor, name in enumerate(names, start=1):
        active: str = " [ACTIVE]" if name == manager.provider_name else ""
        print(f"{nomor}. {name}{active}")
    print("\nKetik exit untuk batal.")

    while True:
        pilihan: str = (await ainput("\nPilih provider: ")).strip()
        if pilihan.lower() == "exit":
            return
        try:
            index: int = int(pilihan) - 1
        except ValueError:
            print("Pilihan tidak valid.")
            continue
        if 0 <= index < len(names):
            manager.set_provider(names[index])
            print(f"Provider aktif: {manager.provider_name}")
            return
        print("Pilihan tidak valid.")


async def pilih_bahasa(manager: VoiceManager) -> None:
    language: str = (await ainput("Kode bahasa, contoh id/en/ja: ")).strip()
    manager.set_language(language)
    print(f"Bahasa aktif: {manager.language}")


def tampilkan_model(models: list[RVCModel]) -> None:
    if not models:
        print("Belum ada model RVC.")
        return
    for nomor, model in enumerate(models, start=1):
        index_name: str = model.index_file.name if model.index_file else "-"
        print(
            f"{nomor}. {model.name} | weight={model.weight_file.name} | index={index_name}"
        )


async def pilih_converter(manager: VoiceManager) -> None:
    names: list[str] = list(CONVERTERS)
    print("\n" + "=" * 40)
    print("VOICE CONVERTERS")
    print("=" * 40)
    for nomor, name in enumerate(names, start=1):
        active: str = " [ACTIVE]" if name == manager.converter_settings.converter else ""
        print(f"{nomor}. {name}{active}")
    print("\nKetik exit untuk batal.")
    while True:
        pilihan: str = (await ainput("\nPilih converter: ")).strip()
        if pilihan.lower() == "exit":
            return
        try:
            index: int = int(pilihan) - 1
        except ValueError:
            print("Pilihan tidak valid.")
            continue
        if 0 <= index < len(names):
            settings: VoiceConverterSettings = set_converter(
                manager.converter_settings,
                names[index],
            )
            await manager.set_converter_settings(settings)
            print(f"Voice converter aktif: {settings.converter}")
            return
        print("Pilihan tidak valid.")


async def pilih_model(manager: VoiceManager) -> None:
    if isinstance(manager.converter, RVCConverter):
        await pilih_model_w_okada(manager, manager.converter)
        return
    models: list[RVCModel] = list_models(RVC_MODELS_FOLDER)
    print("\n" + "=" * 40)
    print("MODEL RVC")
    print("=" * 40)
    tampilkan_model(models)
    if not models:
        return
    print("\nKetik exit untuk batal.")
    while True:
        pilihan: str = (await ainput("\nPilih model: ")).strip()
        if pilihan.lower() == "exit":
            return
        try:
            index: int = int(pilihan) - 1
        except ValueError:
            print("Pilihan tidak valid.")
            continue
        if 0 <= index < len(models):
            settings: VoiceConverterSettings = set_model(
                manager.converter_settings,
                models[index].name,
            )
            await manager.set_converter_settings(settings)
            print(f"Model aktif: {models[index].name}")
            return
        print("Pilihan tidak valid.")


async def pilih_model_w_okada(
    manager: VoiceManager,
    converter: RVCConverter,
) -> None:
    local_models: list[RVCModel] = list_models(RVC_MODELS_FOLDER)
    backend_models: list[WOkadaModel] = await converter.list_models()
    local_names: set[str] = {model.name for model in local_models}
    backend_only: list[WOkadaModel] = [
        model for model in backend_models if model.name not in local_names
    ]
    print("\n" + "=" * 40)
    print("MODEL RVC W-OKADA")
    print("=" * 40)
    if not local_models and not backend_only:
        print("Tidak ada model di models/rvc maupun backend w-okada.")
        return
    for nomor, model in enumerate(local_models, start=1):
        print(f"{nomor}. [LOCAL] {model.name} | {model.weight_file.name}")
    offset: int = len(local_models)
    for nomor, model in enumerate(backend_only, start=offset + 1):
        print(
            f"{nomor}. [BACKEND] slot={model.slot_index} | "
            f"{model.name} | {model.model_file}"
        )
    print("\nKetik exit untuk batal.")
    while True:
        pilihan: str = (await ainput("\nPilih model backend: ")).strip()
        if pilihan.lower() == "exit":
            return
        try:
            index: int = int(pilihan) - 1
        except ValueError:
            print("Pilihan tidak valid.")
            continue
        if 0 <= index < len(local_models):
            local_model: RVCModel = local_models[index]
            print(f"Mendaftarkan model '{local_model.name}' ke w-okada...")
            selected: WOkadaModel = await converter.import_model(local_model)
            settings: VoiceConverterSettings = set_model(
                manager.converter_settings,
                str(selected.slot_index),
            )
            await manager.set_converter_settings(settings)
            print(f"Model backend aktif: slot={selected.slot_index} | {selected.name}")
            return
        backend_index: int = index - offset
        if 0 <= backend_index < len(backend_only):
            selected = backend_only[backend_index]
            settings = set_model(manager.converter_settings, str(selected.slot_index))
            await manager.set_converter_settings(settings)
            print(f"Model backend aktif: slot={selected.slot_index} | {selected.name}")
            return
        print("Pilihan tidak valid.")


async def model_manager(manager: VoiceManager) -> None:
    while True:
        print("\n" + "=" * 40)
        print("MODEL MANAGER")
        print("=" * 40)
        print("1. Import model")
        print("2. List model")
        print("3. Pilih model")
        print("4. Hapus model")
        print("5. Model info")
        print("\nexit = kembali")
        pilihan: str = (await ainput("\nPilih: ")).strip().lower()
        if pilihan == "exit":
            return
        if pilihan == "1":
            source: Path = Path((await ainput("Path file .zip/.pth: ")).strip().strip('"'))
            name: str = (await ainput("Nama model: ")).strip()
            model: RVCModel = import_model(source, RVC_MODELS_FOLDER, name)
            print(f"Model berhasil diimpor: {model.name}")
        elif pilihan == "2":
            tampilkan_model(list_models(RVC_MODELS_FOLDER))
        elif pilihan == "3":
            await pilih_model(manager)
        elif pilihan == "4":
            name = (await ainput("Nama model yang akan dihapus: ")).strip()
            konfirmasi: str = await ainput(f'Ketik "HAPUS {name}" untuk konfirmasi: ')
            if konfirmasi != f"HAPUS {name}":
                print("Dibatalkan.")
                continue
            delete_model(RVC_MODELS_FOLDER, name)
            if manager.converter_settings.model == name:
                await manager.set_converter_settings(
                    set_model(manager.converter_settings, None)
                )
            print(f"Model dihapus: {name}")
        elif pilihan == "5":
            name = (await ainput("Nama model: ")).strip()
            model = get_model(RVC_MODELS_FOLDER, name)
            print(f"Nama   : {model.name}")
            print(f"Folder : {model.folder.resolve()}")
            print(f"Weight : {model.weight_file.name} ({model.weight_file.stat().st_size} byte)")
            print(f"Index  : {model.index_file.name if model.index_file else '-'}")
        else:
            print("Pilihan tidak tersedia.")


async def atur_pitch(manager: VoiceManager) -> None:
    raw_value: str = (await ainput("Pitch (-24 sampai +24): ")).strip()
    settings: VoiceConverterSettings = set_pitch(manager.converter_settings, int(raw_value))
    await manager.set_converter_settings(settings)
    print(f"Pitch aktif: {settings.pitch:+d}")


async def atur_index_ratio(manager: VoiceManager) -> None:
    raw_value: str = (await ainput("Index ratio (0.0 sampai 1.0): ")).strip()
    settings: VoiceConverterSettings = set_index_ratio(
        manager.converter_settings,
        float(raw_value),
    )
    await manager.set_converter_settings(settings)
    print(f"Index ratio aktif: {settings.index_ratio:.2f}")


async def atur_protect(manager: VoiceManager) -> None:
    raw_value: str = (await ainput("Protect (0.0 sampai 1.0): ")).strip()
    settings: VoiceConverterSettings = set_protect(
        manager.converter_settings,
        float(raw_value),
    )
    await manager.set_converter_settings(settings)
    print(f"Protect aktif: {settings.protect:.2f}")


async def generate_test_tts(manager: VoiceManager) -> None:
    text: str = (await ainput("Teks test: ")).strip()
    if not text:
        raise ValueError("Teks test tidak boleh kosong.")
    print("Generating TTS tanpa Discord VC...")
    output: Path = await manager.generate_test(text)
    print(f"TTS sehat. MP3 dibuat: {output.resolve()}")


async def test_suara(ctx: AppContext, manager: VoiceManager) -> None:
    voice_client: discord.VoiceClient | None = await join_voice_channel(ctx)
    if voice_client is None:
        return
    text: str = (await ainput("Teks test: ")).strip()
    if not text:
        raise ValueError("Teks test tidak boleh kosong.")
    print("Generating TTS...")
    if manager.converter_settings.enabled:
        print("Converting voice...")
    print("Playing...")
    await manager.speak(voice_client, text)
    print("Test suara selesai.")


async def disconnect_voice(ctx: AppContext, service: STTService) -> None:
    await service.disable()
    if ctx.guild is None or ctx.guild.voice_client is None:
        print("Bot tidak sedang terhubung ke voice channel.")
        return
    await ctx.guild.voice_client.disconnect(force=False)
    print("Bot keluar dari voice channel.")


@feature("Voice")
async def voice_feature(ctx: AppContext) -> None:
    manager: VoiceManager = VoiceManager.from_config()
    if ctx.client.user is None:
        raise RuntimeError("Identitas bot tidak tersedia untuk Voice System.")
    service: STTService = STTService(
        assistant=ctx.assistant,
        voice_manager=manager,
        settings=load_configured_settings(),
        settings_path=STT_SETTINGS_FILE,
        bot_user_id=ctx.client.user.id,
    )
    if not service.available:
        print(
            "[STT] disabled reason=unsupported_arm "
            f"architecture={service.architecture_label}"
        )
    try:
        existing_client: discord.VoiceClient | None = (
            ctx.guild.voice_client if ctx.guild is not None else None
        )
        if service.available and service.settings.enabled and isinstance(
            existing_client, voice_recv.VoiceRecvClient
        ):
            await service.enable(existing_client)
        await voice_menu(ctx, manager, service)
    finally:
        await service.close()
        await manager.close()


async def terminal_tts_menu(ctx: AppContext, manager: VoiceManager) -> None:
    while True:
        print("\n" + "=" * 55)
        print("                 TERMINAL TTS")
        print("=" * 55)
        connected: bool = ctx.guild is not None and ctx.guild.voice_client is not None
        print(f"Status VC    : {'Connected' if connected else 'Disconnected'}")
        print(f"TTS Provider : {manager.provider_name}")
        print(f"Language     : {manager.language}")
        print("\n1. Kirim TTS / Queue")
        print("2. Pilih TTS provider")
        print("3. Atur bahasa")
        print("4. Generate/Test TTS (tanpa VC)")
        print("5. Speak in VC")
        print("\nexit = kembali")
        pilihan: str = (await ainput("\nPilih: ")).strip().lower()
        if pilihan == "1":
            await terminal_tts(ctx, manager)
        elif pilihan == "2":
            await pilih_provider(manager)
        elif pilihan == "3":
            await pilih_bahasa(manager)
        elif pilihan == "4":
            await generate_test_tts(manager)
        elif pilihan == "5":
            await test_suara(ctx, manager)
        elif pilihan == "exit":
            return
        else:
            print("Pilihan tidak tersedia.")


async def voice_changer_menu(ctx: AppContext, manager: VoiceManager) -> None:
    while True:
        settings: VoiceConverterSettings = manager.converter_settings
        print("\n" + "=" * 55)
        print("                VOICE CHANGER")
        print("=" * 55)
        print(f"Status : {'ON' if settings.enabled else 'OFF'}")
        print(f"Engine : {settings.converter}")
        print(f"Model  : {settings.model or '-'}")
        print(f"Pitch  : {settings.pitch:+d}")
        print("\n1. ON/OFF")
        print("2. Pilih engine")
        print("3. Model Manager")
        print("4. Pilih model")
        print("5. Atur pitch")
        print("6. Atur index ratio")
        print("7. Atur protect")
        print("8. Test output")
        print("\nexit = kembali")
        pilihan: str = (await ainput("\nPilih: ")).strip().lower()
        if pilihan == "1":
            await manager.set_converter_settings(
                set_enabled(settings, not settings.enabled)
            )
            print(f"Voice Converter: {'ON' if not settings.enabled else 'OFF'}")
        elif pilihan == "2":
            await pilih_converter(manager)
        elif pilihan == "3":
            await model_manager(manager)
        elif pilihan == "4":
            await pilih_model(manager)
        elif pilihan == "5":
            await atur_pitch(manager)
        elif pilihan == "6":
            await atur_index_ratio(manager)
        elif pilihan == "7":
            await atur_protect(manager)
        elif pilihan == "8":
            await test_suara(ctx, manager)
        elif pilihan == "exit":
            return
        else:
            print("Pilihan tidak tersedia.")


async def stt_menu(ctx: AppContext, service: STTService) -> None:
    while True:
        settings: STTSettings = service.settings
        print("\n" + "=" * 55)
        print("                  STT SETTINGS")
        print("=" * 55)
        status: str = "UNAVAILABLE (ARM)" if not service.available else (
            "ON" if service.is_running else "OFF"
        )
        print(f"Status          : {status}")
        print(f"Architecture    : {service.architecture_label}")
        print(f"Provider        : {settings.provider}")
        print(f"Model           : {settings.model}")
        print(f"Language        : {settings.language}")
        print(f"VAD             : {'ON' if settings.vad_enabled else 'OFF'}")
        print(f"Wake Word       : {', '.join(settings.wake_words)}")
        print(f"Session Timeout : {settings.voice_session_timeout_seconds:.1f} detik")
        print(f"Max Speech      : {settings.max_utterance_seconds:.1f} detik")
        print(f"Listen Mode     : {settings.listen_mode}")
        print("\n1. STT ON/OFF")
        print("2. Atur model")
        print("3. Atur language")
        print("4. VAD ON/OFF")
        print("5. Atur VAD")
        print("6. Atur wake words")
        print("7. Atur session timeout")
        print("8. Test STT satu utterance")
        print("9. Atur listen mode")
        print("10. Debug transcript ON/OFF")
        print("\nexit = kembali")
        pilihan: str = (await ainput("\nPilih: ")).strip().lower()
        if pilihan == "1":
            if not service.available:
                print("STT tidak tersedia pada perangkat ARM dan tetap OFF.")
                continue
            target_enabled: bool = not settings.enabled
            updated: STTSettings = replace(settings, enabled=target_enabled)
            await service.apply_settings(updated)
            if target_enabled:
                client: voice_recv.VoiceRecvClient | None = await join_voice_channel(ctx)
                if client is None:
                    raise RuntimeError("STT memerlukan voice connection.")
                await service.enable(client)
        elif pilihan == "2":
            model: str = (await ainput("Model Faster Whisper: ")).strip()
            await service.apply_settings(replace(settings, model=model))
        elif pilihan == "3":
            language: str = (await ainput("Language auto/id/en/ja: ")).strip().lower()
            await service.apply_settings(replace(settings, language=language))
        elif pilihan == "4":
            await service.apply_settings(
                replace(settings, vad_enabled=not settings.vad_enabled)
            )
        elif pilihan == "5":
            minimum: float = float(await ainput("Minimum speech detik: "))
            silence: float = float(await ainput("End silence detik: "))
            maximum: float = float(await ainput("Maximum utterance detik: "))
            threshold: int = int(await ainput("RMS threshold: "))
            await service.apply_settings(
                replace(
                    settings,
                    min_speech_seconds=minimum,
                    end_silence_seconds=silence,
                    max_utterance_seconds=maximum,
                    vad_rms_threshold=threshold,
                )
            )
        elif pilihan == "6":
            raw_words: str = await ainput("Wake words, pisahkan koma: ")
            words: tuple[str, ...] = tuple(
                word.strip().casefold() for word in raw_words.split(",") if word.strip()
            )
            await service.apply_settings(replace(settings, wake_words=words))
        elif pilihan == "7":
            timeout: float = float(await ainput("Session timeout detik: "))
            await service.apply_settings(
                replace(settings, voice_session_timeout_seconds=timeout)
            )
        elif pilihan == "8":
            if not service.available:
                print("Test STT tidak tersedia pada perangkat ARM.")
                continue
            client = await join_voice_channel(ctx)
            if client is None:
                raise RuntimeError("STT test memerlukan voice connection.")
            was_running: bool = service.is_running
            print("Silakan bicara satu utterance...")
            try:
                result: STTResult = await service.test_next_utterance(client)
            finally:
                if not was_running and not settings.enabled:
                    await service.disable()
            print(f"Speaker   : {result.user_id}")
            print(f"Duration  : {result.duration_seconds:.3f} s")
            print(f"Language  : {result.language}")
            print(f"Transcript: {result.text}")
            print(f"Latency   : {result.latency_seconds:.3f} s")
        elif pilihan == "9":
            mode: str = (
                await ainput("Mode wake_word/always_active/test_only: ")
            ).strip().lower()
            await service.apply_settings(replace(settings, listen_mode=mode))
        elif pilihan == "10":
            await service.apply_settings(
                replace(settings, log_transcript=not settings.log_transcript)
            )
        elif pilihan == "exit":
            return
        else:
            print("Pilihan tidak tersedia.")


def voice_system_status(
    ctx: AppContext, manager: VoiceManager, service: STTService
) -> None:
    voice_client: discord.VoiceClient | None = (
        ctx.guild.voice_client if ctx.guild is not None else None
    )
    ai_settings = ctx.assistant.settings
    ai_model: str = (
        ai_settings.openrouter_model
        if ai_settings.provider_name == "openrouter"
        else ai_settings.nvidia_nim_model
    )
    converter: VoiceConverterSettings = manager.converter_settings
    print("\n" + "=" * 55)
    print("              VOICE SYSTEM STATUS")
    print("=" * 55)
    print(f"Discord VC       : {'Connected' if voice_client else 'Disconnected'}")
    print(f"Channel          : {voice_client.channel.name if voice_client else '-'}")
    print(f"TTS Provider     : {manager.provider_name}")
    print(f"Voice Changer    : {'ON' if converter.enabled else 'OFF'} ({converter.converter})")
    stt_status: str = "UNAVAILABLE (ARM)" if not service.available else (
        "ON" if service.is_running else "OFF"
    )
    print(f"STT              : {stt_status}")
    print(f"Architecture     : {service.architecture_label}")
    print(f"STT Provider     : {service.settings.provider}")
    print(f"STT Model        : {service.settings.model}")
    print(f"STT Queue        : {service.queue_size}")
    print(f"Voice Sessions   : {service.active_sessions} active")
    print(f"AI Provider      : {ai_settings.provider_name}")
    print(f"AI Model         : {ai_model}")
    print(f"Assistant        : {'Speaking' if service.assistant_speaking else 'Ready'}")


async def voice_menu(
    ctx: AppContext, manager: VoiceManager, service: STTService
) -> None:
    while True:
        print("\n" + "=" * 55)
        print("                  VOICE SYSTEM")
        print("=" * 55)
        print("1. Terminal TTS")
        print("2. Voice Changer")
        print("3. STT")
        print("4. Voice System Status")
        print("5. Connect / Change VC")
        print("6. Disconnect")
        print("\nexit = kembali")
        pilihan: str = (await ainput("\nPilih: ")).strip().lower()
        if pilihan == "1":
            await terminal_tts_menu(ctx, manager)
        elif pilihan == "2":
            await voice_changer_menu(ctx, manager)
        elif pilihan == "3":
            await stt_menu(ctx, service)
        elif pilihan == "4":
            voice_system_status(ctx, manager, service)
        elif pilihan == "5":
            client = await join_voice_channel(ctx)
            if client is not None and service.available and service.settings.enabled:
                await service.enable(client)
        elif pilihan == "6":
            await disconnect_voice(ctx, service)
        elif pilihan == "exit":
            return
        else:
            print("Pilihan tidak tersedia.")
