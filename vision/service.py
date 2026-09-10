"""Lifecycle service connecting webcam observations to Discord expressions."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

from expression.models import ExpressionConversationKey, ExpressionRequest
from vision.engine import ExpressionEvent, ExpressionEventEngine
from vision.expression_bridge import event_to_expression_request
from vision.mediapipe_backend import MediaPipeCameraBackend


class _ChannelMessageAdapter:
    """Minimal message-like object accepted by DiscordExpressionSender.

    Vision reactions are proactive, so there is no Discord message to reply to.
    Adapting reply() to channel.send() lets us reuse the complete existing
    expression resolver/sender pipeline instead of duplicating it.
    """

    def __init__(self, channel: Any) -> None:
        self.channel = channel
        self.guild = getattr(channel, "guild", None)

    async def reply(
        self,
        content: str,
        *,
        mention_author: bool = False,
        allowed_mentions: Any = None,
    ) -> Any:
        del mention_author
        return await self.channel.send(content, allowed_mentions=allowed_mentions)


class VisionReactionService:
    """Run optional computer vision off the asyncio/Discord event loop."""

    def __init__(
        self,
        client: Any,
        expression_service: Any,
        *,
        channel_id: int,
        camera_index: int = 0,
        model_dir: Path = Path("models/vision"),
        calibration_path: Path = Path("data/vision_calibration.json"),
        calibration_seconds: float = 5.0,
        arm_frames: int = 3,
        cooldown_seconds: float = 6.0,
    ) -> None:
        if int(channel_id) <= 0:
            raise ValueError("SENA vision membutuhkan Discord channel_id yang valid")
        self.client = client
        self.expression_service = expression_service
        self.channel_id = int(channel_id)
        self.camera_index = int(camera_index)
        self.model_dir = Path(model_dir)
        self.calibration_path = Path(calibration_path)
        self.calibration_seconds = max(2.0, float(calibration_seconds))
        self.engine = ExpressionEventEngine(
            arm_frames=arm_frames,
            cooldown_seconds=cooldown_seconds,
        )
        self._stop_event = threading.Event()
        self._task: asyncio.Task[None] | None = None
        self._state = "created"
        self._detail = "not started"
        self._last_event: ExpressionEvent | None = None
        self._dispatch_futures: set[Any] = set()

    @property
    def available(self) -> bool:
        return self._state in {"calibrating", "running"}

    def status_detail(self) -> str:
        suffix = (
            f" last={self._last_event.intent}:{self._last_event.confidence:.2f}"
            if self._last_event is not None
            else ""
        )
        return f"{self._state} · {self._detail}{suffix}"

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        loop = asyncio.get_running_loop()
        self._state = "starting"
        self._detail = f"camera={self.camera_index} channel={self.channel_id}"
        self._task = asyncio.create_task(
            asyncio.to_thread(self._worker, loop),
            name="sena-vision-worker",
        )
        # Yield once so immediate startup failures can begin propagating into
        # status without blocking the Discord event loop on camera work.
        await asyncio.sleep(0)

    async def close(self) -> None:
        self._stop_event.set()
        task = self._task
        if task is not None:
            try:
                await task
            finally:
                self._task = None
        self._state = "stopped"
        self._detail = "closed"

    def _worker(self, loop: asyncio.AbstractEventLoop) -> None:
        backend = MediaPipeCameraBackend(
            camera_index=self.camera_index,
            model_dir=self.model_dir,
        )
        try:
            backend.start()
            if not self._load_calibration():
                self._calibrate(backend)
            if self._stop_event.is_set():
                return
            self._state = "running"
            self._detail = f"camera={self.camera_index} calibrated=yes"

            while not self._stop_event.is_set():
                observation = backend.read()
                if observation is None:
                    time.sleep(0.01)
                    continue
                event = self.engine.process(observation)
                if event is None:
                    continue
                request = event_to_expression_request(event)
                if request is None:
                    continue
                self._last_event = event
                future = asyncio.run_coroutine_threadsafe(
                    self._dispatch(event, request),
                    loop,
                )
                self._dispatch_futures.add(future)
                future.add_done_callback(self._on_dispatch_done)
        except Exception as error:
            self._state = "failed"
            self._detail = f"{type(error).__name__}: {error}"
            print(
                f"[SENA VISION] DISABLED runtime error "
                f"type={type(error).__name__} detail={error}"
            )
        finally:
            backend.close()

    def _calibrate(self, backend: MediaPipeCameraBackend) -> None:
        self.engine.reset_calibration()
        self._state = "calibrating"
        self._detail = (
            f"look neutral at camera for {self.calibration_seconds:.1f}s"
        )
        print(
            f"[SENA VISION] calibration started: tatap kamera dengan wajah netral "
            f"selama {self.calibration_seconds:.1f} detik"
        )
        deadline = time.monotonic() + self.calibration_seconds
        samples = 0
        while time.monotonic() < deadline and not self._stop_event.is_set():
            observation = backend.read()
            if (
                observation is not None
                and observation.face_present
                and observation.blendshapes
            ):
                self.engine.add_neutral_sample(observation.blendshapes)
                samples += 1
            else:
                time.sleep(0.01)

        if self._stop_event.is_set():
            return
        minimum_samples = 15
        if samples < minimum_samples:
            raise RuntimeError(
                f"kalibrasi gagal: hanya {samples} frame wajah terbaca; "
                f"butuh >= {minimum_samples}"
            )
        self.engine.finish_calibration(minimum_samples=minimum_samples)
        self._save_calibration()
        print(f"[SENA VISION] calibration complete samples={samples}")

    def _load_calibration(self) -> bool:
        if not self.calibration_path.is_file():
            return False
        try:
            data = json.loads(self.calibration_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("calibration root must be an object")
            self.engine.load_calibration(data)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            print(
                f"[SENA VISION] calibration invalid; recalibrating "
                f"type={type(error).__name__} detail={error}"
            )
            return False
        self._detail = f"loaded calibration={self.calibration_path}"
        print(f"[SENA VISION] calibration loaded path={self.calibration_path}")
        return True

    def _save_calibration(self) -> None:
        data = self.engine.export_calibration()
        self.calibration_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.calibration_path.with_suffix(self.calibration_path.suffix + ".tmp")
        temp.write_text(
            json.dumps(data, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp.replace(self.calibration_path)

    async def _dispatch(
        self,
        event: ExpressionEvent,
        request: ExpressionRequest,
    ) -> None:
        channel = self.client.get_channel(self.channel_id)
        if channel is None:
            channel = await self.client.fetch_channel(self.channel_id)
        if not hasattr(channel, "send"):
            raise TypeError(f"Discord channel {self.channel_id} is not messageable")

        guild = getattr(channel, "guild", None)
        guild_id = int(guild.id) if guild is not None else None
        conversation_key = ExpressionConversationKey(
            source="vision",
            guild_id=guild_id,
            channel_id=int(channel.id),
            participant_id=None,
        )
        adapter = _ChannelMessageAdapter(channel)
        await self.expression_service.sender.send(
            adapter,
            "",
            request,
            True,
            conversation_key,
        )
        print(
            f"[SENA VISION] reaction sent intent={event.intent} "
            f"confidence={event.confidence:.2f} channel={channel.id}"
        )

    def _on_dispatch_done(self, future: Any) -> None:
        self._dispatch_futures.discard(future)
        try:
            future.result()
        except Exception as error:
            print(
                f"[SENA VISION] Discord dispatch failed "
                f"type={type(error).__name__} detail={error}"
            )
