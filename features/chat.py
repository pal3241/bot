import discord

from core.context import AppContext
from core.io import ainput, pilih_channel, pilih_server
from core.registry import feature


def pecah_pesan(pesan: str) -> list[str]:
    return [pesan[index : index + 2000] for index in range(0, len(pesan), 2000)]


def format_pesan_discord(message: discord.Message) -> str:
    bagian: list[str] = []
    if message.content:
        bagian.append(message.content)
    bagian.extend(attachment.url for attachment in message.attachments)
    if not bagian:
        bagian.append("[pesan tanpa teks]")
    return "\n".join(bagian)


async def tampilkan_pesan_discord(message: discord.Message, ctx: AppContext) -> None:
    if not ctx.chat_aktif or ctx.channel is None:
        return
    if message.channel.id != ctx.channel.id:
        return
    if ctx.client.user is not None and message.author.id == ctx.client.user.id:
        return

    print(f"\n{message.author.display_name} > {format_pesan_discord(message)}")
    print("You > ", end="", flush=True)


async def mulai_chat(ctx: AppContext) -> None:
    if ctx.guild is None and await pilih_server(ctx) is None:
        return
    if ctx.channel is None and await pilih_channel(ctx) is None:
        return

    guild: discord.Guild = ctx.guild
    channel: discord.TextChannel = ctx.channel
    print("\n" + "=" * 60)
    print(f"CHAT: {guild.name} -> #{channel.name}")
    print("=" * 60)
    print("Semua teks yang kamu ketik akan dikirim oleh bot.")
    print("Pesan baru dari Discord akan tampil di terminal.")
    print("Ketik exit untuk berhenti.\n")

    ctx.chat_aktif = True
    try:
        while True:
            pesan: str = await ainput("You > ")
            if pesan.strip().lower() == "exit":
                print("\nKeluar dari terminal chat.")
                return
            if not pesan.strip():
                print("BOT > pesan kosong tidak dikirim.")
                continue

            try:
                for chunk in pecah_pesan(pesan):
                    await channel.send(chunk)
            except discord.Forbidden as error:
                raise PermissionError(
                    f"Bot tidak memiliki izin mengirim pesan ke channel '{channel.name}'."
                ) from error
            except discord.HTTPException as error:
                raise RuntimeError(
                    f"Discord API gagal mengirim pesan: status={error.status}, detail={error.text}"
                ) from error
            print(f"BOT > terkirim ke #{channel.name}")
    finally:
        ctx.chat_aktif = False


@feature("Terminal Chat")
async def chat_feature(ctx: AppContext) -> None:
    while True:
        print("\n" + "=" * 55)
        print("             TERMINAL CHAT")
        print("=" * 55)
        print(f"Server : {ctx.guild.name if ctx.guild else 'belum dipilih'}")
        print(f"Channel: #{ctx.channel.name}" if ctx.channel else "Channel: belum dipilih")
        print("\n1. Pilih server")
        print("2. Pilih channel")
        print("3. Mulai chat")
        print("\nexit = kembali")

        pilihan: str = (await ainput("\nPilih: ")).strip().lower()
        if pilihan == "1":
            await pilih_server(ctx)
        elif pilihan == "2":
            await pilih_channel(ctx)
        elif pilihan == "3":
            await mulai_chat(ctx)
        elif pilihan == "exit":
            return
        else:
            print("Pilihan tidak tersedia.")
