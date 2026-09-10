"""Optional desktop webcam backend for SENA Vision.

Imports OpenCV and MediaPipe lazily so the normal Discord bot remains usable on
platforms where those native wheels are unavailable (notably Termux/Android).
"""

from __future__ import annotations

import math
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from vision.engine import VisionObservation


_FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
_HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)


class VisionBackendUnavailable(RuntimeError):
    """Raised when the optional camera/CV runtime cannot be started."""


class MediaPipeCameraBackend:
    """Capture webcam frames and convert them to backend-neutral observations."""

    def __init__(
        self,
        *,
        camera_index: int = 0,
        model_dir: Path = Path("models/vision"),
        width: int = 640,
        height: int = 480,
    ) -> None:
        self.camera_index = int(camera_index)
        self.model_dir = Path(model_dir)
        self.width = int(width)
        self.height = int(height)
        self._cv2: Any | None = None
        self._mp: Any | None = None
        self._capture: Any | None = None
        self._face_detector: Any | None = None
        self._hand_detector: Any | None = None
        self._t0 = 0.0
        self._last_timestamp_ms = -1

    def start(self) -> None:
        if self._capture is not None:
            return
        try:
            import cv2  # type: ignore
            import mediapipe as mp  # type: ignore
            from mediapipe.tasks import python as mp_tasks  # type: ignore
            from mediapipe.tasks.python import vision  # type: ignore
        except Exception as error:
            raise VisionBackendUnavailable(
                "OpenCV/MediaPipe belum tersedia. Install optional vision dependencies."
            ) from error

        self.model_dir.mkdir(parents=True, exist_ok=True)
        face_model = self._ensure_model("face_landmarker.task", _FACE_MODEL_URL)
        hand_model = self._ensure_model("hand_landmarker.task", _HAND_MODEL_URL)

        try:
            face_options = vision.FaceLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(model_asset_path=str(face_model)),
                running_mode=vision.RunningMode.VIDEO,
                num_faces=1,
                output_face_blendshapes=True,
            )
            hand_options = vision.HandLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(model_asset_path=str(hand_model)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=2,
            )
            face_detector = vision.FaceLandmarker.create_from_options(face_options)
            hand_detector = vision.HandLandmarker.create_from_options(hand_options)
        except Exception as error:
            raise VisionBackendUnavailable(f"MediaPipe detector gagal dibuat: {error}") from error

        capture = cv2.VideoCapture(self.camera_index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not capture.isOpened():
            face_detector.close()
            hand_detector.close()
            capture.release()
            raise VisionBackendUnavailable(
                f"Webcam index {self.camera_index} tidak dapat dibuka."
            )

        self._cv2 = cv2
        self._mp = mp
        self._capture = capture
        self._face_detector = face_detector
        self._hand_detector = hand_detector
        self._t0 = time.monotonic()
        self._last_timestamp_ms = -1

    def close(self) -> None:
        for detector_name in ("_face_detector", "_hand_detector"):
            detector = getattr(self, detector_name)
            if detector is not None:
                try:
                    detector.close()
                finally:
                    setattr(self, detector_name, None)
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._cv2 = None
        self._mp = None

    def read(self) -> VisionObservation | None:
        if self._capture is None:
            raise RuntimeError("MediaPipeCameraBackend.start() harus dipanggil lebih dulu.")
        ok, frame = self._capture.read()
        if not ok or frame is None:
            return None

        cv2 = self._cv2
        mp = self._mp
        timestamp_ms = self._next_timestamp_ms()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        face_result = self._face_detector.detect_for_video(image, timestamp_ms)
        hand_result = self._hand_detector.detect_for_video(image, timestamp_ms)

        face_landmarks = face_result.face_landmarks[0] if face_result.face_landmarks else None
        blendshapes: dict[str, float] = {}
        if face_result.face_blendshapes:
            for category in face_result.face_blendshapes[0]:
                name = getattr(category, "category_name", None)
                if name:
                    blendshapes[str(name)] = float(category.score)

        hands = list(hand_result.hand_landmarks or ())
        gestures = self._detect_gestures(face_landmarks, hands, blendshapes)
        return VisionObservation(
            blendshapes=blendshapes,
            gestures=frozenset(gestures),
            face_present=face_landmarks is not None,
        )

    def _ensure_model(self, name: str, url: str) -> Path:
        path = self.model_dir / name
        if path.is_file() and path.stat().st_size > 0:
            return path
        temp = path.with_suffix(path.suffix + ".download")
        try:
            urllib.request.urlretrieve(url, temp)
            temp.replace(path)
        except Exception as error:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise VisionBackendUnavailable(
                f"Gagal mengunduh model MediaPipe {name}: {error}"
            ) from error
        return path

    def _next_timestamp_ms(self) -> int:
        current = int((time.monotonic() - self._t0) * 1000)
        current = max(current, self._last_timestamp_ms + 1)
        self._last_timestamp_ms = current
        return current

    @classmethod
    def _detect_gestures(
        cls,
        face: Any | None,
        hands: list[Any],
        blendshapes: dict[str, float],
    ) -> set[str]:
        gestures: set[str] = set()

        if len(hands) >= 2:
            first, second = hands[0], hands[1]
            if (
                cls._distance(first[8], second[8]) < 0.09
                and cls._distance(first[4], second[4]) < 0.09
            ):
                gestures.add("heart")

        if face is not None:
            min_x = min(point.x for point in face)
            max_x = max(point.x for point in face)
            min_y = min(point.y for point in face)
            max_y = max(point.y for point in face)
            pad_x = (max_x - min_x) * 0.22
            pad_y = (max_y - min_y) * 0.18

            for hand in hands:
                if not cls._open_palm(hand):
                    continue
                palm_x, palm_y = cls._palm_center(hand)
                if (
                    min_x - pad_x <= palm_x <= max_x + pad_x
                    and min_y - pad_y <= palm_y <= max_y + pad_y
                ):
                    gestures.add("facepalm")
                elif hand[0].y < max_y + 0.15 and hand[8].y < hand[0].y:
                    gestures.add("hand_up")

        tongue = blendshapes.get("tongueOut", 0.0)
        if tongue >= 0.35:
            gestures.add("tongue_out")

        look_left = min(
            blendshapes.get("eyeLookOutLeft", 0.0),
            blendshapes.get("eyeLookInRight", 0.0),
        )
        look_right = min(
            blendshapes.get("eyeLookInLeft", 0.0),
            blendshapes.get("eyeLookOutRight", 0.0),
        )
        if max(look_left, look_right) >= 0.38:
            gestures.add("side_eye")

        return gestures

    @staticmethod
    def _distance(a: Any, b: Any) -> float:
        return math.hypot(float(a.x) - float(b.x), float(a.y) - float(b.y))

    @staticmethod
    def _palm_center(hand: Any) -> tuple[float, float]:
        points: Iterable[Any] = (hand[index] for index in (0, 5, 9, 13, 17))
        coords = [(float(point.x), float(point.y)) for point in points]
        return (
            sum(x for x, _ in coords) / len(coords),
            sum(y for _, y in coords) / len(coords),
        )

    @staticmethod
    def _open_palm(hand: Any) -> bool:
        # Image coordinates grow downward. Requiring three extended fingers is
        # intentionally tolerant of camera rotation and imperfect tracking.
        extended = 0
        for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
            if hand[tip].y < hand[pip].y:
                extended += 1
        return extended >= 3

    def __enter__(self) -> "MediaPipeCameraBackend":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
