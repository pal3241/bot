import asyncio
import os

import discord
from dotenv import load_dotenv

import features.emoji
import features.chat
import features.voice
from core.context import AppContext
from core.io import ainput
from core.registry import FEATURES, Feature
from features.chat import tampilkan_pesan_discord


async def main_menu(ctx: AppContext) -> None:
    while True:
        if ctx.client.user is None:
            raise RuntimeError("Identitas bot tidak tersedia setelah client siap.")

        print("\n" + "=" * 60)
        print("          DISCORD BOT MANAGER")
        print("=" * 60)
        print(f"Bot: {ctx.client.user}")
        print(f"Server aktif: {ctx.guild.name if ctx.guild else 'belum dipilih'}")

        features: list[tuple[str, Feature]] = list(FEATURES.items())
        for nomor, (name, _) in enumerate(features, start=1):
            print(f"{nomor}. {name}")
        print("\nexit = tutup program")

        pilihan: str = (await ainput("\nPilih fitur: ")).strip().lower()
        if pilihan == "exit":
            print("\nMenutup bot...")
            return

        try:
            index: int = int(pilihan) - 1
        except ValueError:
            print("Pilihan tidak valid.")
            continue

        if 0 <= index < len(features):
            _, function = features[index]
            await function(ctx)
        else:
            print("Pilihan tidak valid.")


async def run(token: str) -> None:
    intents: discord.Intents = discord.Intents.default()
    intents.message_content = True
    client: discord.Client = discord.Client(intents=intents)
    ctx: AppContext = AppContext(client=client)

    async def on_message(message: discord.Message) -> None:
        await tampilkan_pesan_discord(message, ctx)

    client.event(on_message)
    await client.login(token)
    discord_task: asyncio.Task[None] = asyncio.create_task(client.connect(reconnect=True))

    try:
        await client.wait_until_ready()
        if client.user is None:
            raise RuntimeError("Discord client siap tetapi identitas bot tidak tersedia.")
        print("\n" + "=" * 60)
        print("BOT ONLINE")
        print("=" * 60)
        print(f"Bot     : {client.user}")
        print(f"Bot ID  : {client.user.id}")
        print(f"Servers : {len(client.guilds)}")
        await main_menu(ctx)
    finally:
        if not client.is_closed():
            await client.close()
        await discord_task


def get_token() -> str:
    load_dotenv()
    token: str | None = os.getenv("TOKEN")
    if token is None or not token.strip():
        raise RuntimeError("TOKEN tidak ditemukan atau kosong di file .env.")
    return token


if __name__ == "__main__":
    asyncio.run(run(get_token()))
