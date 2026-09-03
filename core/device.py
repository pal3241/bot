from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from enum import Enum


class DeviceKind(str, Enum):
    ANDROID = "android"
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    kind: DeviceKind
    system: str
    machine: str
    python_version: str
    python_implementation: str
    is_termux: bool
    is_android: bool
    is_desktop: bool


def detect_device() -> DeviceInfo:
    system = platform.system().strip() or sys.platform
    machine = platform.machine().strip() or "unknown"
    lowered_system = system.casefold()
    is_termux = bool(os.getenv("TERMUX_VERSION")) or "/com.termux/" in sys.executable
    is_android = sys.platform == "android" or is_termux

    if is_android:
        kind = DeviceKind.ANDROID
    elif lowered_system == "windows":
        kind = DeviceKind.WINDOWS
    elif lowered_system == "linux":
        kind = DeviceKind.LINUX
    elif lowered_system == "darwin":
        kind = DeviceKind.MACOS
    else:
        kind = DeviceKind.UNKNOWN

    return DeviceInfo(
        kind=kind,
        system=system,
        machine=machine,
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
        is_termux=is_termux,
        is_android=is_android,
        is_desktop=kind in {DeviceKind.WINDOWS, DeviceKind.LINUX, DeviceKind.MACOS},
    )


def format_device_summary(info: DeviceInfo) -> str:
    return (
        f"platform={info.kind.value} system={info.system} machine={info.machine} "
        f"python={info.python_version} implementation={info.python_implementation} "
        f"termux={'yes' if info.is_termux else 'no'}"
    )
