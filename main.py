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
from core.registry import FEATURES
from core.runtime_log import install_runtime_log_capture, restore_runtime_log_capture
from core.runtime_status import RuntimeStatus

MessageDisplay = Callable[[discord.Message, AppContext], Awaitable[None]]


async def main_menu(
    ctx: AppContext,
    device: DeviceInfo,
    feature_results: dict[str, FeatureLoadResult],
) -> None:
    while True:
        if ctx.client.user is None:
            raise RuntimeError("Identitas bot tidak tersedia setelah client siap.")
        print("\n" + "=" * 60)
        print("          DISCORD BOT MANAGER")
        print("=" * 60)
        print(f"Bot          : {ctx.client.user}")
        print(f"Device       : {device.kind.value} / {device.machine}")
        print(f"Python       : {device.python_version}")
        print(f"Server aktif : {ctx.guild.name if ctx.guild else 'belum dipilih'}")
        print(f"Runtime      : {feature_health_summary(feature_results)}")
        features = list(FEATURES.items())
        for nomor, (name, _) in enumerate(features, start=1):
            print(f"{nomor}. {name}")
        print("\nstatus = lihat health semua fitur")
        print("exit   = tutup program")
        pilihan = (await ainput("\nPilih fitur: ")).strip().lower()
        if pilihan == "exit":
            print("\nMenutup bot...")
            return
        if pilihan == "status":
            print("\n" + "-" * 60)
            print("RUNTIME FEATURE HEALTH")
            print("-" * 60)
            for result in feature_results.values():
                print(
                    f"{result.spec.label:<24} "
                    f"{result.state.value.upper():<10} {result.detail}"
                )
            print(
                f"AI Assistant{' ':<12} "
                f"{'ENABLED' if ctx.assistant is not None else 'DISABLED'}"
            )
            print(
                f"Scheduler{' ':<15} "
                f"{'ENABLED' if ctx.scheduler is not None and ctx.scheduler.available else 'DISABLED'}"
            )
            print(
                f"Music{' ':<19} "
                f"{'ENABLED' if ctx.music is not None and ctx.music.available else 'DISABLED'}"
            )
            continue
        try:
            index = int(pilihan) - 1
        except ValueError:
            print("Pilihan tidak valid.")
            continue
        if not 0 <= index < len(features):
            print("Pilihan tidak valid.")
            continue
        name, function = features[index]
        try:
            await function(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(
                f"\n[FEATURE ISOLATED] {name} gagal: "
                f"{type(error).__name__}: {error}"
            )
            print("Fitur lain tetap aktif. Kembali ke menu utama.")


def _load_message_display(
    feature_results: dict[str, FeatureLoadResult],
) -> MessageDisplay | None:
    chat_result = feature_results.get("chat")
    if chat_result is None or chat_result.module is None:
        return None
    candidate = getattr(chat_result.module, "tampilkan_pesan_discord", None)
    return candidate if callable(candidate) else None


async def _build_assistant_safely() -> Any | None:
    try:
        from assistant import build_assistant_manager

        assistant = build_assistant_manager()
        await assistant.initialize()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        print(
            f"[SUBSYSTEM] AI Assistant: DISABLED "
            f"({type(error).__name__}: {error})"
        )
        return None
    print("[SUBSYSTEM] AI Assistant: ENABLED")
    return assistant


def _build_scheduler_safely(client: discord.Client) -> Any | None:
    try:
        from scheduler import SchedulerManager

        scheduler = SchedulerManager(client, Path("data/sena_schedule.db"))
    except Exception as error:
        print(
            f"[SUBSYSTEM] Scheduler: DISABLED "
            f"({type(error).__name__}: {error})"
        )
        return None
    print("[SUBSYSTEM] Scheduler: CREATED (starts after Discord ready)")
    return scheduler


def _build_music_safely(
    client: discord.Client,
    scheduler: Any | None,
) -> Any | None:
    try:
        from music import MusicManager

        music = MusicManager(client, Path("config/music.json"))
        if scheduler is not None:
            music.attach_scheduler(scheduler)
    except Exception as error:
        print(
            f"[SUBSYSTEM] Music: DISABLED "
            f"({type(error).__name__}: {error})"
        )
        return None
    print(f"[SUBSYSTEM] Music: CREATED {music.backend_status()}")
    return music


def _build_router_safely(
    client: discord.Client,
    assistant: Any | None,
    scheduler: Any | None,
    music: Any | None,
) -> tuple[Any | None, Any | None, Any | None]:
    if assistant is None:
        print("[SUBSYSTEM] Discord AI Router: SKIPPED (AI Assistant unavailable)")
        return None, None, None
    try:
        from actions import build_action_executor
        from assistant.discord import DiscordMessageRouter
        from expression.service import ExpressionService

        expression_service = ExpressionService(
            client,
            Path("config/expressions.json"),
            Path("assets/expressions/gifs"),
        )
        action_executor = build_action_executor(scheduler, music)
        assistant.attach_action_registry(action_executor.registry)
        router = DiscordMessageRouter(
            client,
            assistant,
            expression_service.sender,
            action_executor,
        )
    except Exception as error:
        print(
            f"[SUBSYSTEM] Discord AI Router/Action/Expression: DISABLED "
            f"({type(error).__name__}: {error})"
        )
        return None, None, None
    print(
        f"[SUBSYSTEM] Action System: ENABLED "
        f"tools={','.join(action_executor.registry.names)}"
    )
    print("[SUBSYSTEM] Discord AI Router/Expression: ENABLED")
    return router, expression_service, action_executor


def _build_runtime_status(
    assistant: Any | None,
    message_router: Any | None,
    expression_service: Any | None,
    action_executor: Any | None,
) -> RuntimeStatus:
    tools: tuple[str, ...] = ()
    if action_executor is not None:
        try:
            tools = tuple(action_executor.registry.names)
        except Exception:
            tools = ()
    return RuntimeStatus(
        ai_enabled=assistant is not None,
        router_enabled=message_router is not None,
        action_enabled=action_executor is not None,
        expression_enabled=expression_service is not None,
        action_tools=tools,
    )


def _build_flet_ui_safely(
    ctx: AppContext,
    device: DeviceInfo,
    feature_results: dict[str, FeatureLoadResult],
    runtime_status: RuntimeStatus,
) -> Any | None:
    if os.getenv("SENA_UI", "flet").strip().casefold() == "terminal":
        print("[SUBSYSTEM] Flet UI: SKIPPED (SENA_UI=terminal)")
        return None
    try:
        from ui import SenaFletUI

        ui = SenaFletUI(ctx, device, feature_results, runtime_status)
    except Exception as error:
        print(f"[SUBSYSTEM] Flet UI: DISABLED ({type(error).__name__}: {error})")
        return None
    print(
        f"[SUBSYSTEM] Flet UI: ENABLED "
        f"mode={'web' if device.is_android else 'desktop'}"
    )
    return ui


async def run(token: str) -> None:
    device = detect_device()
    print("\n" + "=" * 60)
    print("SENNA SAFE STARTUP")
    print("=" * 60)
    print(f"[DEVICE] {format_device_summary(device)}")
    print("[STARTUP] Memuat fitur satu per satu; kegagalan diisolasi.\n")

    feature_results = load_features(device)
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True
    client = discord.Client(intents=intents)

    assistant = await _build_assistant_safely()
    scheduler = _build_scheduler_safely(client)
    music = _build_music_safely(client, scheduler)
    ctx = AppContext(
        client=client,
        assistant=assistant,
        device=device,
        scheduler=scheduler,
        music=music,
    )
    message_display = _load_message_display(feature_results)
    message_router, expression_service, action_executor = _build_router_safely(
        client,
        assistant,
        scheduler,
        music,
    )
    runtime_status = _build_runtime_status(
        assistant,
        message_router,
        expression_service,
        action_executor,
    )
    flet_ui: Any | None = None

    async def on_message(message: discord.Message) -> None:
        if flet_ui is not None:
            try:
                await flet_ui.notify_discord_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                print(
                    f"[SENA UI] Discord message bridge gagal: "
                    f"{type(error).__name__}: {error}"
                )
        if message_display is not None:
            try:
                await message_display(message, ctx)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                print(
                    f"[FEATURE RUNTIME] Terminal Chat display gagal: "
                    f"{type(error).__name__}: {error}"
                )
        if message_router is not None:
            try:
                await message_router.handle(message)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                print(
                    f"[SUBSYSTEM RUNTIME] Discord AI Router gagal: "
                    f"{type(error).__name__}: {error}"
                )

    client.event(on_message)
    await client.login(token)
    discord_task = asyncio.create_task(client.connect(reconnect=True))
    try:
        await client.wait_until_ready()
        if client.user is None:
            raise RuntimeError(
                "Discord client siap tetapi identitas bot tidak tersedia."
            )

        if music is not None:
            try:
                await music.start()
            except Exception as error:
                print(
                    f"[SUBSYSTEM] Music start gagal: "
                    f"{type(error).__name__}: {error}; bot tetap berjalan"
                )

        if scheduler is not None:
            try:
                await scheduler.start()
            except Exception as error:
                print(
                    f"[SUBSYSTEM] Scheduler start gagal: "
                    f"{type(error).__name__}: {error}; bot tetap berjalan"
                )

        if expression_service is not None:
            try:
                expression_service.refresh_runtime()
            except Exception as error:
                print(
                    f"[SUBSYSTEM] Expression runtime refresh gagal: "
                    f"{type(error).__name__}: {error}; text bot tetap berjalan"
                )

        print("\n" + "=" * 60)
        print("BOT ONLINE - DEGRADED MODE SUPPORTED")
        print("=" * 60)
        print(f"Bot      : {client.user}")
        print(f"Bot ID   : {client.user.id}")
        print(f"Servers  : {len(client.guilds)}")
        print(f"Device   : {device.kind.value} ({device.machine})")
        print(f"Features : {feature_health_summary(feature_results)}")
        print(f"Runtime  : {runtime_status.summary()}")
        print(
            f"Scheduler: {'ONLINE' if scheduler is not None and scheduler.available else 'OFFLINE'}"
        )
        print(
            f"Music    : {'ONLINE' if music is not None and music.available else 'OFFLINE'}"
            + (f" · {music.backend_status()}" if music is not None else "")
        )

        flet_ui = _build_flet_ui_safely(
            ctx,
            device,
            feature_results,
            runtime_status,
        )
        if flet_ui is not None:
            try:
                await flet_ui.run()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                print(
                    f"[SUBSYSTEM] Flet UI runtime gagal: "
                    f"{type(error).__name__}: {error}"
                )
                print("[SUBSYSTEM] Beralih ke terminal fallback.")
                await main_menu(ctx, device, feature_results)
        else:
            await main_menu(ctx, device, feature_results)
    finally:
        if scheduler is not None:
            try:
                await scheduler.close()
            except Exception as error:
                print(
                    f"[SHUTDOWN] Scheduler close gagal: "
                    f"{type(error).__name__}: {error}"
                )
        if music is not None:
            try:
                await music.close()
            except Exception as error:
                print(
                    f"[SHUTDOWN] Music close gagal: "
                    f"{type(error).__name__}: {error}"
                )
        if assistant is not None:
            try:
                await assistant.close()
            except Exception as error:
                print(
                    f"[SHUTDOWN] AI close gagal: "
                    f"{type(error).__name__}: {error}"
                )
        if not client.is_closed():
            await client.close()
        await discord_task


def get_token() -> str:
    load_dotenv()
    token = os.getenv("TOKEN")
    if token is None or not token.strip():
        raise RuntimeError("TOKEN tidak ditemukan atau kosong di file .env.")
    return token


if __name__ == "__main__":
    install_runtime_log_capture()
    try:
        asyncio.run(run(get_token()))
    finally:
        restore_runtime_log_capture()
