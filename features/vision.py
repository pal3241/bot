"""Terminal controller for SENA's optional local webcam reactions."""

from __future__ import annotations

from config import (
    SENA_VISION_CALIBRATION_FILE,
    SENA_VISION_CALIBRATION_SECONDS,
    SENA_VISION_CAMERA_INDEX,
    SENA_VISION_COOLDOWN_SECONDS,
    SENA_VISION_MODEL_DIR,
)
from core.context import AppContext
from core.io import ainput, pilih_channel
from core.registry import feature
from vision.service import VisionReactionService


def _build_service(ctx: AppContext) -> VisionReactionService:
    if ctx.channel is None:
        raise RuntimeError("Pilih text channel Vision terlebih dahulu.")
    if ctx.expression_service is None:
        raise RuntimeError("Expression Service tidak aktif.")
    return VisionReactionService(
        ctx.client,
        ctx.expression_service,
        channel_id=int(ctx.channel.id),
        camera_index=SENA_VISION_CAMERA_INDEX,
        model_dir=SENA_VISION_MODEL_DIR,
        calibration_path=SENA_VISION_CALIBRATION_FILE,
        calibration_seconds=SENA_VISION_CALIBRATION_SECONDS,
        cooldown_seconds=SENA_VISION_COOLDOWN_SECONDS,
    )


@feature("Vision / Webcam")
async def vision_menu(ctx: AppContext) -> None:
    if ctx.device is not None and ctx.device.is_android:
        print("[SENA VISION] MediaPipe webcam backend tidak didukung di Android/Termux.")
        return
    if ctx.expression_service is None:
        print("[SENA VISION] Expression Service tidak aktif; vision tidak dapat mengirim reaction.")
        return

    service: VisionReactionService | None = None
    started = False

    async def ensure_service() -> VisionReactionService | None:
        nonlocal service
        if ctx.channel is None and await pilih_channel(ctx) is None:
            return None
        if service is None or service.channel_id != int(ctx.channel.id):
            service = _build_service(ctx)
        return service

    try:
        while True:
            channel_label = (
                f"#{ctx.channel.name} ({ctx.channel.guild.name})"
                if ctx.channel is not None
                else "belum dipilih"
            )
            status = service.status_detail() if service is not None else "stopped · not started"

            print("\n" + "-" * 60)
            print("SENA VISION / WEBCAM")
            print("-" * 60)
            print(f"Status  : {status}")
            print(f"Camera  : {SENA_VISION_CAMERA_INDEX}")
            print(f"Channel : {channel_label}")
            print("\nchannel     = pilih / ganti output text channel")
            print("start       = mulai deteksi")
            print("status      = tampilkan status")
            print("recalibrate = hapus calibration lalu kalibrasi ulang")
            print("stop        = hentikan vision")
            print("exit        = stop dan kembali ke menu utama")
            command = (await ainput("vision> ")).strip().casefold()

            if command == "channel":
                was_running = started
                if started and service is not None:
                    await service.close()
                    started = False
                selected = await pilih_channel(ctx)
                if selected is None:
                    if was_running and service is not None:
                        await service.start()
                        started = True
                    continue
                service = _build_service(ctx)
                print(
                    f"[SENA VISION] output channel aktif: "
                    f"#{selected.name} ({selected.guild.name})"
                )
                if was_running:
                    await service.start()
                    started = True
                    print("[SENA VISION] worker dimulai ulang pada channel baru.")

            elif command == "start":
                if started:
                    print("Vision sudah berjalan.")
                    continue
                current = await ensure_service()
                if current is None:
                    continue
                await current.start()
                started = True
                print("Vision worker dimulai. Kamera diproses di thread terpisah.")

            elif command == "status":
                print(service.status_detail() if service is not None else status)

            elif command == "recalibrate":
                current = await ensure_service()
                if current is None:
                    continue
                if started:
                    await current.close()
                    started = False
                try:
                    SENA_VISION_CALIBRATION_FILE.unlink(missing_ok=True)
                except OSError as error:
                    print(f"Gagal menghapus calibration: {error}")
                    continue
                current.engine.reset_calibration()
                await current.start()
                started = True
                print("Kalibrasi lama dihapus; tatap kamera dengan ekspresi netral.")

            elif command == "stop":
                if started and service is not None:
                    await service.close()
                    started = False
                print("Vision berhenti.")

            elif command == "exit":
                return

            else:
                print("Perintah tidak dikenal.")
    finally:
        if started and service is not None:
            await service.close()
