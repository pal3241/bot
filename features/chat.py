import asyncio

import discord

from core.context import AppContext
from core.io import ainput, pilih_channel, pilih_server
from core.registry import feature


_TERMINAL_SEND_QUEUE_SIZE: int = 32


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

    print(
        f"\n{message.author.display_name} > {format_pesan_discord(message)}",
        flush=True,
    )
    print("You > ", end="", flush=True)


async def _send_terminal_message(
    channel: discord.TextChannel,
    pesan: str,
) -> None:
    for chunk in pecah_pesan(pesan):
        await channel.send(chunk)


async def _terminal_send_worker(
    channel: discord.TextChannel,
    queue: asyncio.Queue[str | None],
) -> None:
    while True:
        pesan: str | None = await queue.get()
        try:
            if pesan is None:
                return
            try:
                await _send_terminal_message(channel, pesan)
            except discord.Forbidden:
                print(
                    f"\nBOT > gagal: tidak punya izin kirim ke #{channel.name}",
                    flush=True,
                )
            except discord.HTTPException as error:
                print(
                    f"\nBOT > Discord API error status={error.status}: {error.text}",
                    flush=True,
                )
            except (OSError, RuntimeError) as error:
                print(
                    f"\nBOT > gagal kirim: {type(error).__name__}: {error}",
                    flush=True,
                )
            else:
                print(f"\nBOT > terkirim ke #{channel.name}", flush=True)
        finally:
            queue.task_done()


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
    print("Semua teks yang kamu ketik akan masuk antrean kirim tanpa memblok terminal.")
    print("Pesan baru dari Discord akan tampil langsung di terminal.")
    print("Ketik exit untuk berhenti.\n", flush=True)

    send_queue: asyncio.Queue[str | None] = asyncio.Queue(
        maxsize=_TERMINAL_SEND_QUEUE_SIZE
    )
    sender_task: asyncio.Task[None] = asyncio.create_task(
        _terminal_send_worker(channel, send_queue),
        name="sena-terminal-send-worker",
    )

    ctx.chat_aktif = True
    try:
        while True:
            pesan: str = await ainput("You > ")
            if pesan.strip().lower() == "exit":
                print("\nKeluar dari terminal chat.", flush=True)
                return
            if not pesan.strip():
                print("BOT > pesan kosong tidak dikirim.", flush=True)
                continue

            try:
                send_queue.put_nowait(pesan)
            except asyncio.QueueFull:
                print(
                    "\nBOT > antrean kirim penuh, tunggu sebentar lalu coba lagi.",
                    flush=True,
                )
            else:
                print("BOT > masuk antrean kirim.", flush=True)
    finally:
        ctx.chat_aktif = False
        # Finish already queued messages, then stop the worker cleanly.
        await send_queue.join()
        await send_queue.put(None)
        await sender_task


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
        print("\nexit = kembali", flush=True)

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
            print("Pilihan tidak tersedia.", flush=True)
