import discord

from core.context import AppContext
from core.io import ainput, pilih_server
from core.registry import feature
from voice.manager import VoiceManager
from voice.queue import TTSQueue
from voice.registry import PROVIDERS


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
        if queue.worker is not None and not queue.worker.done():
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


async def disconnect_voice(ctx: AppContext) -> None:
    if ctx.guild is None or ctx.guild.voice_client is None:
        print("Bot tidak sedang terhubung ke voice channel.")
        return
    await ctx.guild.voice_client.disconnect(force=False)
    print("Bot keluar dari voice channel.")


@feature("Voice TTS")
async def voice_feature(ctx: AppContext) -> None:
    manager: VoiceManager = VoiceManager.from_config()
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
        print("\n1. Pilih server")
        print("2. Pilih voice channel")
        print("3. Join VC")
        print("4. Terminal TTS Queue")
        print("5. Pilih TTS Engine")
        print("6. Pilih bahasa")
        print("7. Disconnect")
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
            await disconnect_voice(ctx)
        elif pilihan == "exit":
            return
        else:
            print("Pilihan tidak tersedia.")
