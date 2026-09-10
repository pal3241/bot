"""Backend-independent SENA vision expression engine.

Inspired by the useful design idea in gazijarin/itsgiving: calibrate against the
current user's neutral face instead of relying only on universal raw thresholds.
No code/assets are copied from that project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import fmean, pstdev
from time import monotonic
from typing import Mapping


@dataclass(slots=True, frozen=True)
class VisionObservation:
    """Normalised observation emitted by a future MediaPipe/OpenCV backend."""

    blendshapes: Mapping[str, float] = field(default_factory=dict)
    gestures: frozenset[str] = field(default_factory=frozenset)
    face_present: bool = True


@dataclass(slots=True, frozen=True)
class ExpressionEvent:
    """Semantic event safe to pass to SENA's expression resolver."""

    intent: str
    confidence: float
    source: str = "vision"


class ExpressionEventEngine:
    """Calibrate facial channels and emit stable semantic expression events.

    The engine intentionally does not know Discord IDs, emoji names, GIF URLs,
    cameras, or MediaPipe.  This keeps vision optional and lets the existing
    expression resolver decide how an intent should be rendered.
    """

    DEFAULT_RULES = {
        "shocked": {"jawOpen": 5.0, "eyeWideLeft": 2.0, "eyeWideRight": 2.0},
        "happy": {"mouthSmileLeft": 4.0, "mouthSmileRight": 4.0},
        "disgusted": {"noseSneerLeft": 4.0, "noseSneerRight": 4.0},
    }
    GESTURE_INTENTS = {
        "heart": "love",
        "hand_up": "greeting",
        "side_eye": "suspicious",
        "tongue_out": "playful",
        "facepalm": "facepalm",
    }

    def __init__(self, *, arm_frames: int = 3, cooldown_seconds: float = 4.0) -> None:
        self.arm_frames = max(1, int(arm_frames))
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self._samples: list[dict[str, float]] = []
        self._mean: dict[str, float] = {}
        self._std: dict[str, float] = {}
        self._candidate: str | None = None
        self._candidate_frames = 0
        self._last_emit: dict[str, float] = {}

    @property
    def calibrated(self) -> bool:
        return bool(self._mean)

    def reset_calibration(self) -> None:
        self._samples.clear()
        self._mean.clear()
        self._std.clear()
        self._candidate = None
        self._candidate_frames = 0

    def add_neutral_sample(self, blendshapes: Mapping[str, float]) -> None:
        self._samples.append({k: float(v) for k, v in blendshapes.items()})

    def finish_calibration(self, *, minimum_samples: int = 15) -> None:
        if len(self._samples) < minimum_samples:
            raise ValueError(f"need at least {minimum_samples} neutral samples")
        channels = set().union(*(sample.keys() for sample in self._samples))
        for channel in channels:
            values = [sample.get(channel, 0.0) for sample in self._samples]
            self._mean[channel] = fmean(values)
            # A small floor prevents an almost-motionless calibration from
            # turning tiny detector noise into enormous z-scores.
            self._std[channel] = max(pstdev(values), 0.01)
        self._samples.clear()

    def z_scores(self, blendshapes: Mapping[str, float]) -> dict[str, float]:
        if not self.calibrated:
            return {}
        return {
            channel: (float(value) - self._mean.get(channel, 0.0))
            / self._std.get(channel, 0.01)
            for channel, value in blendshapes.items()
        }

    def process(self, observation: VisionObservation) -> ExpressionEvent | None:
        if not observation.face_present:
            return self._arm("away", 1.0)

        for gesture, intent in self.GESTURE_INTENTS.items():
            if gesture in observation.gestures:
                return self._arm(intent, 1.0)

        scores = self.z_scores(observation.blendshapes)
        if not scores:
            self._clear_candidate()
            return None

        for intent, requirements in self.DEFAULT_RULES.items():
            ratios = [scores.get(name, 0.0) / threshold for name, threshold in requirements.items()]
            if ratios and min(ratios) >= 1.0:
                confidence = min(1.0, min(ratios) / 2.0)
                return self._arm(intent, confidence)

        self._clear_candidate()
        return None

    def _arm(self, intent: str, confidence: float) -> ExpressionEvent | None:
        if self._candidate == intent:
            self._candidate_frames += 1
        else:
            self._candidate = intent
            self._candidate_frames = 1

        if self._candidate_frames < self.arm_frames:
            return None

        now = monotonic()
        if now - self._last_emit.get(intent, float("-inf")) < self.cooldown_seconds:
            return None
        self._last_emit[intent] = now
        self._clear_candidate()
        return ExpressionEvent(intent=intent, confidence=max(0.0, min(1.0, confidence)))

    def _clear_candidate(self) -> None:
        self._candidate = None
        self._candidate_frames = 0
