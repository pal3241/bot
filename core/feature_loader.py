from __future__ import annotations

import importlib
import traceback
from dataclasses import dataclass
from enum import Enum
from types import ModuleType

from core.device import DeviceInfo


class FeatureLoadState(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    key: str
    module: str
    label: str
    allow_android: bool = True
    allow_desktop: bool = True


@dataclass(frozen=True, slots=True)
class FeatureLoadResult:
    spec: FeatureSpec
    state: FeatureLoadState
    detail: str
    module: ModuleType | None = None

    @property
    def available(self) -> bool:
        return self.state is FeatureLoadState.ENABLED


DEFAULT_FEATURE_SPECS: tuple[FeatureSpec, ...] = (
    FeatureSpec("emoji", "features.emoji", "Emoji Manager"),
    FeatureSpec("chat", "features.chat", "Terminal Chat"),
    FeatureSpec("ai", "features.ai", "AI Settings"),
    # TTS synthesis is intentionally checked independently from Discord voice receive.
    # gTTS works on Android/Termux even when discord-ext-voice-recv/Faster Whisper do not.
    FeatureSpec("tts", "voice.providers.gtts_provider", "TTS / gTTS"),
    FeatureSpec("voice", "features.voice", "Discord Voice / STT"),
)


def _platform_allowed(spec: FeatureSpec, device: DeviceInfo) -> bool:
    if device.is_android:
        return spec.allow_android
    if device.is_desktop:
        return spec.allow_desktop
    return True


def load_feature(spec: FeatureSpec, device: DeviceInfo) -> FeatureLoadResult:
    if not _platform_allowed(spec, device):
        return FeatureLoadResult(
            spec=spec,
            state=FeatureLoadState.SKIPPED,
            detail=f"not supported on {device.kind.value}",
        )
    try:
        module = importlib.import_module(spec.module)
    except (ImportError, ModuleNotFoundError) as error:
        return FeatureLoadResult(
            spec=spec,
            state=FeatureLoadState.DISABLED,
            detail=f"missing dependency: {type(error).__name__}: {error}",
        )
    except Exception as error:  # isolate feature import failures from the app
        traceback.print_exc()
        return FeatureLoadResult(
            spec=spec,
            state=FeatureLoadState.FAILED,
            detail=f"startup error: {type(error).__name__}: {error}",
        )
    return FeatureLoadResult(
        spec=spec,
        state=FeatureLoadState.ENABLED,
        detail="loaded",
        module=module,
    )


def load_features(
    device: DeviceInfo,
    specs: tuple[FeatureSpec, ...] = DEFAULT_FEATURE_SPECS,
) -> dict[str, FeatureLoadResult]:
    results: dict[str, FeatureLoadResult] = {}
    for spec in specs:
        result = load_feature(spec, device)
        results[spec.key] = result
        print(
            f"[FEATURE] {spec.label}: {result.state.value.upper()} "
            f"({result.detail})"
        )
    return results


def feature_health_summary(results: dict[str, FeatureLoadResult]) -> str:
    enabled = sum(result.available for result in results.values())
    total = len(results)
    return f"features={enabled}/{total} enabled"
