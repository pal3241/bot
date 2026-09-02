from pathlib import Path

import discord

from config import RVC_MODELS_FOLDER
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


async def join_voice_channel(ctx: AppContext) -> discord.VoiceClient | None:
    if ctx.voice_channel is None and await pilih_voice_channel(ctx) is None:
        return None
    channel: discord.VoiceChannel = ctx.voice_channel
    existing_client: discord.VoiceClient | None = channel.guild.voice_client

    try:
        if existing_client is not None and existing_client.is_connected():
            if existing_client.channel.id != channel.id:
                await existing_client.move_to(channel)
            print(f"Bot terhubung ke VC: {channel.name}")
            return existing_client
        voice_client: discord.VoiceClient = await channel.connect()
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
    print("Ketik exit untuk menunggu antrean selesai dan kembali.\n")
    try:
        while True:
            queue.raise_worker_error()
            text: str = await ainput("TTS > ")
            if text.strip().lower() == "exit":
                print("Menunggu TTS queue selesai...")
                await queue.finish()
                return
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


async def disconnect_voice(ctx: AppContext) -> None:
    if ctx.guild is None or ctx.guild.voice_client is None:
        print("Bot tidak sedang terhubung ke voice channel.")
        return
    await ctx.guild.voice_client.disconnect(force=False)
    print("Bot keluar dari voice channel.")


@feature("Voice TTS")
async def voice_feature(ctx: AppContext) -> None:
    manager: VoiceManager = VoiceManager.from_config()
    try:
        await voice_menu(ctx, manager)
    finally:
        await manager.close()


async def voice_menu(ctx: AppContext, manager: VoiceManager) -> None:
    while True:
        connected_channel: str = "belum terhubung"
        if ctx.guild is not None and ctx.guild.voice_client is not None:
            connected_channel = ctx.guild.voice_client.channel.name

        print("\n" + "=" * 55)
        print("              VOICE MANAGER")
        print("=" * 55)
        print(f"Server      : {ctx.guild.name if ctx.guild else 'belum dipilih'}")
        print(f"Voice target: {ctx.voice_channel.name if ctx.voice_channel else 'belum dipilih'}")
        print(f"Terhubung   : {connected_channel}")
        print(f"TTS Engine  : {manager.provider_name}")
        print(f"Language    : {manager.language}")
        settings: VoiceConverterSettings = manager.converter_settings
        converter_status: str = "ON" if settings.enabled else "OFF"
        print(f"Converter   : {converter_status} ({settings.converter})")
        print(f"Model       : {settings.model or '-'}")
        print(
            f"Pitch       : {settings.pitch:+d} | Index: {settings.index_ratio:.2f} | "
            f"Protect: {settings.protect:.2f}"
        )
        print("\n1. Pilih server")
        print("2. Pilih voice channel")
        print("3. Join VC")
        print("4. Terminal TTS Queue")
        print("5. Pilih TTS Engine")
        print("6. Pilih bahasa")
        print("7. Voice Converter ON/OFF")
        print("8. Pilih converter")
        print("9. Model Manager")
        print("10. Pilih model")
        print("11. Atur pitch")
        print("12. Atur index ratio")
        print("13. Atur protect")
        print("14. Test suara")
        print("15. Disconnect")
        print("\nexit = kembali")

        pilihan: str = (await ainput("\nPilih: ")).strip().lower()
        if pilihan == "1":
            await pilih_server(ctx)
        elif pilihan == "2":
            await pilih_voice_channel(ctx)
        elif pilihan == "3":
            await join_voice_channel(ctx)
        elif pilihan == "4":
            await terminal_tts(ctx, manager)
        elif pilihan == "5":
            await pilih_provider(manager)
        elif pilihan == "6":
            await pilih_bahasa(manager)
        elif pilihan == "7":
            await manager.set_converter_settings(
                set_enabled(settings, not settings.enabled)
            )
            print(f"Voice Converter: {'ON' if not settings.enabled else 'OFF'}")
        elif pilihan == "8":
            await pilih_converter(manager)
        elif pilihan == "9":
            await model_manager(manager)
        elif pilihan == "10":
            await pilih_model(manager)
        elif pilihan == "11":
            await atur_pitch(manager)
        elif pilihan == "12":
            await atur_index_ratio(manager)
        elif pilihan == "13":
            await atur_protect(manager)
        elif pilihan == "14":
            await test_suara(ctx, manager)
        elif pilihan == "15":
            await disconnect_voice(ctx)
        elif pilihan == "exit":
            return
        else:
            print("Pilihan tidak tersedia.")
