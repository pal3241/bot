from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

import discord
from dotenv import load_dotenv

from core.context import AppContext
from core.device import DeviceInfo, detect_device, format_device_summary
from core.feature_loader import FeatureLoadResult, feature_health_summary, load_features
from core.io import ainput
from core.registry import FEATURES, Feature

MessageDisplay = Callable[[discord.Message, AppContext], Awaitable[None]]


async def main_menu(ctx: AppContext, device: DeviceInfo, feature_results: dict[str, FeatureLoadResult]) -> None:
    while True:
        if ctx.client.user is None: raise RuntimeError("Identitas bot tidak tersedia setelah client siap.")
        print("\n" + "=" * 60); print("          DISCORD BOT MANAGER"); print("=" * 60)
        print(f"Bot          : {ctx.client.user}"); print(f"Device       : {device.kind.value} / {device.machine}"); print(f"Python       : {device.python_version}")
        print(f"Server aktif : {ctx.guild.name if ctx.guild else 'belum dipilih'}"); print(f"Runtime      : {feature_health_summary(feature_results)}")
        features = list(FEATURES.items())
        for nomor, (name, _) in enumerate(features, start=1): print(f"{nomor}. {name}")
        print("\nstatus = lihat health semua fitur"); print("exit   = tutup program")
        pilihan = (await ainput("\nPilih fitur: ")).strip().lower()
        if pilihan == "exit": print("\nMenutup bot..."); return
        if pilihan == "status":
            print("\n" + "-" * 60); print("RUNTIME FEATURE HEALTH"); print("-" * 60)
            for result in feature_results.values(): print(f"{result.spec.label:<24} {result.state.value.upper():<10} {result.detail}")
            print(f"AI Assistant{' ':<12} {'ENABLED' if ctx.assistant is not None else 'DISABLED'}"); continue
        try: index = int(pilihan) - 1
        except ValueError: print("Pilihan tidak valid."); continue
        if not 0 <= index < len(features): print("Pilihan tidak valid."); continue
        name, function = features[index]
        try: await function(ctx)
        except asyncio.CancelledError: raise
        except Exception as error:
            print(f"\n[FEATURE ISOLATED] {name} gagal: {type(error).__name__}: {error}"); print("Fitur lain tetap aktif. Kembali ke menu utama.")


def _load_message_display(feature_results: dict[str, FeatureLoadResult]) -> MessageDisplay | None:
    chat_result = feature_results.get("chat")
    if chat_result is None or chat_result.module is None: return None
    candidate = getattr(chat_result.module, "tampilkan_pesan_discord", None)
    return candidate if callable(candidate) else None


async def _build_assistant_safely() -> Any | None:
    try:
        from assistant import build_assistant_manager
        assistant = build_assistant_manager(); await assistant.initialize()
    except asyncio.CancelledError: raise
    except Exception as error: print(f"[SUBSYSTEM] AI Assistant: DISABLED ({type(error).__name__}: {error})"); return None
    print("[SUBSYSTEM] AI Assistant: ENABLED"); return assistant


def _build_router_safely(client: discord.Client, assistant: Any | None) -> tuple[Any | None, Any | None, Any | None]:
    if assistant is None:
        print("[SUBSYSTEM] Discord AI Router: SKIPPED (AI Assistant unavailable)"); return None, None, None
    try:
        from actions import build_action_executor
        from assistant.discord import DiscordMessageRouter
        from expression.service import ExpressionService
        expression_service = ExpressionService(client, Path("config/expressions.json"), Path("assets/expressions/gifs"))
        action_executor = build_action_executor()
        assistant.attach_action_registry(action_executor.registry)
        router = DiscordMessageRouter(client, assistant, expression_service.sender, action_executor)
    except Exception as error:
        print(f"[SUBSYSTEM] Discord AI Router/Action/Expression: DISABLED ({type(error).__name__}: {error})"); return None, None, None
    print(f"[SUBSYSTEM] Action System: ENABLED tools={','.join(action_executor.registry.names)}")
    print("[SUBSYSTEM] Discord AI Router/Expression: ENABLED")
    return router, expression_service, action_executor


def _build_flet_ui_safely(ctx: AppContext, device: DeviceInfo, feature_results: dict[str, FeatureLoadResult]) -> Any | None:
    if os.getenv("SENA_UI", "flet").strip().casefold() == "terminal":
        print("[SUBSYSTEM] Flet UI: SKIPPED (SENA_UI=terminal)")
        return None
    try:
        from ui import SenaFletUI
        ui = SenaFletUI(ctx, device, feature_results)
    except Exception as error:
        print(f"[SUBSYSTEM] Flet UI: DISABLED ({type(error).__name__}: {error})")
        return None
    print(f"[SUBSYSTEM] Flet UI: ENABLED mode={'web' if device.is_android else 'desktop'}")
    return ui


async def run(token: str) -> None:
    device = detect_device(); print("\n" + "=" * 60); print("SENNA SAFE STARTUP"); print("=" * 60); print(f"[DEVICE] {format_device_summary(device)}"); print("[STARTUP] Memuat fitur satu per satu; kegagalan diisolasi.\n")
    feature_results = load_features(device)
    intents = discord.Intents.default(); intents.message_content = True; intents.voice_states = True
    client = discord.Client(intents=intents)
    assistant = await _build_assistant_safely(); ctx = AppContext(client=client, assistant=assistant, device=device)
    message_display = _load_message_display(feature_results)
    message_router, expression_service, _action_executor = _build_router_safely(client, assistant)
    flet_ui: Any | None = None

    async def on_message(message: discord.Message) -> None:
        if flet_ui is not None:
            try: await flet_ui.notify_discord_message(message)
            except asyncio.CancelledError: raise
            except Exception as error: print(f"[SENA UI] Discord message bridge gagal: {type(error).__name__}: {error}")
        if message_display is not None:
            try: await message_display(message, ctx)
            except asyncio.CancelledError: raise
            except Exception as error: print(f"[FEATURE RUNTIME] Terminal Chat display gagal: {type(error).__name__}: {error}")
        if message_router is not None:
            try: await message_router.handle(message)
            except asyncio.CancelledError: raise
            except Exception as error: print(f"[SUBSYSTEM RUNTIME] Discord AI Router gagal: {type(error).__name__}: {error}")

    client.event(on_message); await client.login(token); discord_task = asyncio.create_task(client.connect(reconnect=True))
    try:
        await client.wait_until_ready()
        if client.user is None: raise RuntimeError("Discord client siap tetapi identitas bot tidak tersedia.")
        if expression_service is not None:
            try: expression_service.refresh_runtime()
            except Exception as error: print(f"[SUBSYSTEM] Expression runtime refresh gagal: {type(error).__name__}: {error}; text bot tetap berjalan")
        print("\n" + "=" * 60); print("BOT ONLINE - DEGRADED MODE SUPPORTED"); print("=" * 60)
        print(f"Bot      : {client.user}"); print(f"Bot ID   : {client.user.id}"); print(f"Servers  : {len(client.guilds)}"); print(f"Device   : {device.kind.value} ({device.machine})"); print(f"Features : {feature_health_summary(feature_results)}"); print(f"AI       : {'enabled' if assistant is not None else 'disabled'}")

        flet_ui = _build_flet_ui_safely(ctx, device, feature_results)
        if flet_ui is not None:
            try:
                await flet_ui.run()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                print(f"[SUBSYSTEM] Flet UI runtime gagal: {type(error).__name__}: {error}")
                print("[SUBSYSTEM] Beralih ke terminal fallback.")
                await main_menu(ctx, device, feature_results)
        else:
            await main_menu(ctx, device, feature_results)
    finally:
        if assistant is not None:
            try: await assistant.close()
            except Exception as error: print(f"[SHUTDOWN] AI close gagal: {type(error).__name__}: {error}")
        if not client.is_closed(): await client.close()
        await discord_task


def get_token() -> str:
    load_dotenv(); token = os.getenv("TOKEN")
    if token is None or not token.strip(): raise RuntimeError("TOKEN tidak ditemukan atau kosong di file .env.")
    return token


if __name__ == "__main__": asyncio.run(run(get_token()))
