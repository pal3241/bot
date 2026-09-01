import webbrowser
from pathlib import Path

import discord

from config import GIF_FOLDER, MAX_EMOJI_SIZE
from core.context import AppContext
from core.io import ainput, pilih_server
from core.registry import feature


def buat_nama_emoji(existing_names: set[str]) -> str:
    nomor: int = 1
    while True:
        name: str = f"emoji{nomor:04d}"
        if name not in existing_names:
            return name
        nomor += 1


async def tambah_emoji(ctx: AppContext) -> None:
    if ctx.guild is None and await pilih_server(ctx) is None:
        return
    guild: discord.Guild = ctx.guild

    if not GIF_FOLDER.is_dir():
        raise FileNotFoundError(f"Folder GIF tidak ditemukan: {GIF_FOLDER}")

    files: list[Path] = sorted(GIF_FOLDER.glob("*.gif"))
    if not files:
        print(f"\nTidak ada GIF di folder: {GIF_FOLDER}")
        return

    print("\n" + "=" * 55)
    print("BULK EMOJI UPLOAD")
    print("=" * 55)
    print(f"Server : {guild.name}")
    print(f"GIF    : {len(files)}")

    existing_names: set[str] = {emoji.name for emoji in guild.emojis}
    berhasil: int = 0
    gagal: int = 0
    dilewati: int = 0

    for nomor, file_path in enumerate(files, start=1):
        size: int = file_path.stat().st_size
        size_kb: float = size / 1024
        print(f"\n[{nomor}/{len(files)}] {file_path.name}")

        if size > MAX_EMOJI_SIZE:
            print(f"SKIP -> {size_kb:.1f} KB (maksimum {MAX_EMOJI_SIZE / 1024:.0f} KB)")
            dilewati += 1
            continue

        emoji_name: str = buat_nama_emoji(existing_names)
        try:
            emoji: discord.Emoji = await guild.create_custom_emoji(
                name=emoji_name,
                image=file_path.read_bytes(),
                reason="Bulk emoji uploader",
            )
        except discord.Forbidden as error:
            raise PermissionError(
                f"Bot tidak memiliki izin mengelola emoji di server '{guild.name}'."
            ) from error
        except discord.HTTPException as error:
            gagal += 1
            print(f"GAGAL -> Discord API status={error.status}, detail={error.text}")
            continue

        existing_names.add(emoji.name)
        berhasil += 1
        print(f"OK -> {emoji.name} ({size_kb:.1f} KB)")

    print("\n" + "=" * 55)
    print(f"Berhasil : {berhasil}")
    print(f"Skip     : {dilewati}")
    print(f"Gagal    : {gagal}")


async def lihat_emoji(ctx: AppContext) -> None:
    if ctx.guild is None and await pilih_server(ctx) is None:
        return
    guild: discord.Guild = ctx.guild
    emojis: tuple[discord.Emoji, ...] = guild.emojis

    print("\n" + "=" * 55)
    print(f"EMOJI - {guild.name}")
    print("=" * 55)
    if not emojis:
        print("Belum ada emoji.")
        return

    for nomor, emoji in enumerate(emojis, start=1):
        tipe: str = "GIF" if emoji.animated else "STATIC"
        print(f"{nomor}. {emoji.name} [{tipe}]")
    print(f"\nTotal: {len(emojis)}")


async def hapus_semua_emoji(ctx: AppContext) -> None:
    if ctx.guild is None and await pilih_server(ctx) is None:
        return
    guild: discord.Guild = ctx.guild
    emojis: list[discord.Emoji] = [emoji for emoji in guild.emojis if not emoji.managed]
    if not emojis:
        print("\nTidak ada emoji yang dapat dihapus.")
        return

    print(f"\nAkan menghapus {len(emojis)} emoji dari {guild.name}.")
    konfirmasi: str = await ainput('\nKetik "HAPUS" untuk konfirmasi: ')
    if konfirmasi != "HAPUS":
        print("Dibatalkan.")
        return

    berhasil: int = 0
    gagal: int = 0
    for nomor, emoji in enumerate(emojis, start=1):
        print(f"[{nomor}/{len(emojis)}] {emoji.name}")
        try:
            await guild.delete_emoji(emoji, reason="Bulk emoji delete")
        except discord.Forbidden as error:
            raise PermissionError(
                f"Bot tidak memiliki izin menghapus emoji di server '{guild.name}'."
            ) from error
        except discord.HTTPException as error:
            gagal += 1
            print(f"GAGAL -> Discord API status={error.status}, detail={error.text}")
            continue
        berhasil += 1
        print("OK")

    print(f"\nBerhasil: {berhasil}")
    print(f"Gagal   : {gagal}")


async def invite_bot(ctx: AppContext) -> None:
    if ctx.client.user is None:
        raise RuntimeError("Identitas bot belum tersedia karena client belum siap.")

    permissions: discord.Permissions = discord.Permissions.none()
    permissions.view_channel = True
    permissions.send_messages = True
    permissions.manage_expressions = True
    url: str = discord.utils.oauth_url(
        ctx.client.user.id,
        permissions=permissions,
        scopes=("bot",),
    )
    print(f"\nLINK INVITE:\n{url}")
    pilihan: str = await ainput("\nBuka browser? [y/n]: ")
    if pilihan.strip().lower() == "y":
        if not webbrowser.open(url):
            raise RuntimeError(f"Browser gagal dibuka. Buka URL ini secara manual: {url}")


@feature("Emoji Manager")
async def emoji_feature(ctx: AppContext) -> None:
    while True:
        print("\n" + "=" * 55)
        print("             EMOJI MANAGER")
        print("=" * 55)
        print(f"Server: {ctx.guild.name if ctx.guild else 'belum dipilih'}")
        print("\n1. Pilih server")
        print("2. Tambah semua GIF")
        print("3. Hapus semua emoji")
        print("4. Lihat emoji")
        print("5. Invite bot")
        print("\nexit = kembali")

        pilihan: str = (await ainput("\nPilih: ")).strip().lower()
        if pilihan == "1":
            await pilih_server(ctx)
        elif pilihan == "2":
            await tambah_emoji(ctx)
        elif pilihan == "3":
            await hapus_semua_emoji(ctx)
        elif pilihan == "4":
            await lihat_emoji(ctx)
        elif pilihan == "5":
            await invite_bot(ctx)
        elif pilihan == "exit":
            return
        else:
            print("Pilihan tidak tersedia.")

