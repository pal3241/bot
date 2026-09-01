import asyncio

import discord

from core.context import AppContext


async def ainput(text: str) -> str:
    return await asyncio.to_thread(input, text)


async def pilih_server(ctx: AppContext) -> discord.Guild | None:
    guilds: list[discord.Guild] = list(ctx.client.guilds)
    if not guilds:
        print("\nBot belum masuk server mana pun.")
        return None

    print("\n" + "=" * 50)
    print("PILIH SERVER")
    print("=" * 50)
    for nomor, guild in enumerate(guilds, start=1):
        print(f"{nomor}. {guild.name} [{guild.id}]")
    print("\nKetik exit untuk batal.")

    while True:
        pilihan: str = (await ainput("\nPilih server: ")).strip()
        if pilihan.lower() == "exit":
            return None

        try:
            index: int = int(pilihan) - 1
        except ValueError:
            print("Pilihan tidak valid.")
            continue

        if 0 <= index < len(guilds):
            ctx.guild = guilds[index]
            ctx.channel = None
            ctx.voice_channel = None
            print(f"\nServer aktif: {ctx.guild.name}")
            return ctx.guild

        print("Pilihan tidak valid.")


async def pilih_channel(ctx: AppContext) -> discord.TextChannel | None:
    if ctx.guild is None and await pilih_server(ctx) is None:
        return None

    guild: discord.Guild = ctx.guild
    channels: list[discord.TextChannel] = list(guild.text_channels)
    if not channels:
        print("\nServer tidak memiliki text channel.")
        return None

    print("\n" + "=" * 50)
    print(f"CHANNEL - {guild.name}")
    print("=" * 50)
    for nomor, channel in enumerate(channels, start=1):
        print(f"{nomor}. #{channel.name}")
    print("\nKetik exit untuk batal.")

    while True:
        pilihan: str = (await ainput("\nPilih channel: ")).strip()
        if pilihan.lower() == "exit":
            return None

        try:
            index: int = int(pilihan) - 1
        except ValueError:
            print("Pilihan tidak valid.")
            continue

        if 0 <= index < len(channels):
            ctx.channel = channels[index]
            print(f"\nChannel aktif: #{ctx.channel.name}")
            return ctx.channel

        print("Pilihan tidak valid.")
