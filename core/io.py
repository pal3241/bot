import asyncio
import os
import sys

import discord

from core.context import AppContext


async def _posix_ainput(text: str) -> str:
    """Read one terminal line without occupying a worker thread.

    Termux/Linux event loops can watch stdin directly. This keeps the default thread
    pool free for other work and makes Discord event handling stay responsive while the
    terminal is waiting for input.
    """

    loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
    fd: int = sys.stdin.fileno()
    future: asyncio.Future[str] = loop.create_future()

    def ready() -> None:
        try:
            line: str = sys.stdin.readline()
        except Exception as error:
            if not future.done():
                future.set_exception(error)
            return
        finally:
            try:
                loop.remove_reader(fd)
            except (NotImplementedError, OSError, ValueError):
                pass

        if not future.done():
            if line == "":
                future.set_exception(EOFError("stdin ditutup"))
            else:
                future.set_result(line.rstrip("\r\n"))

    loop.add_reader(fd, ready)
    print(text, end="", flush=True)
    try:
        return await future
    finally:
        try:
            loop.remove_reader(fd)
        except (NotImplementedError, OSError, ValueError):
            pass


async def ainput(text: str) -> str:
    if os.name == "posix":
        try:
            return await _posix_ainput(text)
        except (NotImplementedError, OSError, ValueError):
            # Some embedded/redirected terminals do not expose a selectable stdin.
            pass
    return await asyncio.to_thread(input, text)


async def pilih_server(ctx: AppContext) -> discord.Guild | None:
    guilds: list[discord.Guild] = list(ctx.client.guilds)
    if not guilds:
        print("\nBot belum masuk server mana pun.", flush=True)
        return None

    print("\n" + "=" * 50)
    print("PILIH SERVER")
    print("=" * 50)
    for nomor, guild in enumerate(guilds, start=1):
        print(f"{nomor}. {guild.name} [{guild.id}]")
    print("\nKetik exit untuk batal.", flush=True)

    while True:
        pilihan: str = (await ainput("\nPilih server: ")).strip()
        if pilihan.lower() == "exit":
            return None

        try:
            index: int = int(pilihan) - 1
        except ValueError:
            print("Pilihan tidak valid.", flush=True)
            continue

        if 0 <= index < len(guilds):
            ctx.guild = guilds[index]
            ctx.channel = None
            ctx.voice_channel = None
            print(f"\nServer aktif: {ctx.guild.name}", flush=True)
            return ctx.guild

        print("Pilihan tidak valid.", flush=True)


async def pilih_channel(ctx: AppContext) -> discord.TextChannel | None:
    if ctx.guild is None and await pilih_server(ctx) is None:
        return None

    guild: discord.Guild = ctx.guild
    channels: list[discord.TextChannel] = list(guild.text_channels)
    if not channels:
        print("\nServer tidak memiliki text channel.", flush=True)
        return None

    print("\n" + "=" * 50)
    print(f"CHANNEL - {guild.name}")
    print("=" * 50)
    for nomor, channel in enumerate(channels, start=1):
        print(f"{nomor}. #{channel.name}")
    print("\nKetik exit untuk batal.", flush=True)

    while True:
        pilihan: str = (await ainput("\nPilih channel: ")).strip()
        if pilihan.lower() == "exit":
            return None

        try:
            index: int = int(pilihan) - 1
        except ValueError:
            print("Pilihan tidak valid.", flush=True)
            continue

        if 0 <= index < len(channels):
            ctx.channel = channels[index]
            print(f"\nChannel aktif: #{ctx.channel.name}", flush=True)
            return ctx.channel

        print("Pilihan tidak valid.", flush=True)
