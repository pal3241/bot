"""Terminal controller for SENA's optional local webcam reactions."""

from __future__ import annotations

from config import (
    SENA_VISION_CALIBRATION_FILE,
    SENA_VISION_CALIBRATION_SECONDS,
    SENA_VISION_CAMERA_INDEX,
    SENA_VISION_CHANNEL_ID,
    SENA_VISION_COOLDOWN_SECONDS,
    SENA_VISION_ENABLED,
    SENA_VISION_MODEL_DIR,
)
from core.context import AppContext
from core.io import ainput
from core.registry import feature
from vision.service import VisionReactionService


def _resolve_channel_id(ctx: AppContext) -> int:
    if SENA_VISION_CHANNEL_ID > 0:
        return SENA_VISION_CHANNEL_ID
    if ctx.channel is not None:
        return int(ctx.channel.id)
    return 0


@feature("Vision / Webcam")
async def vision_menu(ctx: AppContext) -> None:
    if ctx.device is not None and ctx.device.is_android:
        print("[SENA VISION] MediaPipe webcam backend tidak didukung di Android/Termux.")
        return
    if ctx.expression_service is None:
        print("[SENA VISION] Expression Service tidak aktif; vision tidak dapat mengirim reaction.")
        return

    channel_id = _resolve_channel_id(ctx)
    if channel_id <= 0:
        raw = (await ainput("Discord channel ID untuk reaction vision: ")).strip()
        try:
            channel_id = int(raw)
        except ValueError:
            print("Channel ID tidak valid.")
            return
        if channel_id <= 0:
            print("Channel ID tidak valid.")
            return

    service = VisionReactionService(
        ctx.client,
        ctx.expression_service,
        channel_id=channel_id,
        camera_index=SENA_VISION_CAMERA_INDEX,
        model_dir=SENA_VISION_MODEL_DIR,
        calibration_path=SENA_VISION_CALIBRATION_FILE,
        calibration_seconds=SENA_VISION_CALIBRATION_SECONDS,
        cooldown_seconds=SENA_VISION_COOLDOWN_SECONDS,
    )

    started = False
    try:
        if SENA_VISION_ENABLED:
            await service.start()
            started = True
            print("[SENA VISION] auto-start aktif dari SENA_VISION_ENABLED=true")

        while True:
            print("\n" + "-" * 60)
            print("SENA VISION / WEBCAM")
            print("-" * 60)
            print(f"Status  : {service.status_detail()}")
            print(f"Camera  : {SENA_VISION_CAMERA_INDEX}")
            print(f"Channel : {channel_id}")
            print("\nstart       = mulai deteksi")
            print("status      = tampilkan status")
            print("recalibrate = hapus calibration lalu kalibrasi ulang")
            print("stop        = hentikan vision")
            print("exit        = stop dan kembali ke menu utama")
            command = (await ainput("vision> ")).strip().casefold()

            if command == "start":
                if started:
                    print("Vision sudah berjalan.")
                    continue
                await service.start()
                started = True
                print("Vision worker dimulai. Kamera diproses di thread terpisah.")
            elif command == "status":
                print(service.status_detail())
            elif command == "recalibrate":
                if started:
                    await service.close()
                    started = False
                try:
                    SENA_VISION_CALIBRATION_FILE.unlink(missing_ok=True)
                except OSError as error:
                    print(f"Gagal menghapus calibration: {error}")
                    continue
                # close() marks the service stopped but start() is restartable.
                service.engine.reset_calibration()
                await service.start()
                started = True
                print("Kalibrasi lama dihapus; tatap kamera dengan ekspresi netral.")
            elif command == "stop":
                if started:
                    await service.close()
                    started = False
                print("Vision berhenti.")
            elif command == "exit":
                return
            else:
                print("Perintah tidak dikenal.")
    finally:
        if started:
            await service.close()
