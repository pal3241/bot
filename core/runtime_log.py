from __future__ import annotations

import io
import sys
import threading
from collections import deque
from typing import Any


class RuntimeLogBuffer:
    def __init__(self, max_lines: int = 2000) -> None:
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._lock = threading.RLock()

    def append_text(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            for line in text.replace("\r", "").splitlines():
                if line.strip():
                    self._lines.append(line)

    def snapshot(self) -> list[str]:
        with self._lock:
            return list(self._lines)

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()


RUNTIME_LOGS = RuntimeLogBuffer()


class _RuntimeTee(io.TextIOBase):
    def __init__(self, original: Any) -> None:
        self._original = original

    def write(self, text: str) -> int:
        written = self._original.write(text)
        self._original.flush()
        RUNTIME_LOGS.append_text(text)
        return written

    def flush(self) -> None:
        self._original.flush()


_installed = False
_original_stdout: Any | None = None
_original_stderr: Any | None = None


def install_runtime_log_capture() -> None:
    global _installed, _original_stdout, _original_stderr
    if _installed:
        return
    _original_stdout = sys.stdout
    _original_stderr = sys.stderr
    sys.stdout = _RuntimeTee(sys.stdout)
    sys.stderr = _RuntimeTee(sys.stderr)
    _installed = True
    RUNTIME_LOGS.append_text("[SENA LOG] runtime capture enabled")


def restore_runtime_log_capture() -> None:
    global _installed
    if not _installed:
        return
    if _original_stdout is not None:
        sys.stdout = _original_stdout
    if _original_stderr is not None:
        sys.stderr = _original_stderr
    _installed = False


# Flet imports this module when the control center is built. Start capturing at that
# point automatically so Settings always receives subsequent runtime logs without a
# second wrapper/subclass layer.
install_runtime_log_capture()
