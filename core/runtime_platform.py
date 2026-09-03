import os
import platform


def normalize_architecture(value: str) -> str:
    return value.strip().casefold().replace("-", "").replace("_", "")


def is_arm_architecture(value: str) -> bool:
    normalized: str = normalize_architecture(value)
    return normalized.startswith("arm") or normalized.startswith("aarch64")


def runtime_architectures() -> tuple[str, ...]:
    candidates: tuple[str, ...] = (
        platform.machine(),
        os.getenv("PROCESSOR_ARCHITECTURE", ""),
        os.getenv("PROCESSOR_ARCHITEW6432", ""),
    )
    return tuple(dict.fromkeys(value.strip() for value in candidates if value.strip()))


def runtime_is_arm() -> bool:
    return any(is_arm_architecture(value) for value in runtime_architectures())
