import json
from dataclasses import asdict, dataclass
from pathlib import Path

from config import (
    STT_LANGUAGE,
    STT_MODEL,
    STT_PROVIDER,
    STT_QUEUE_SIZE,
    STT_SETTINGS_FILE,
    STT_VAD_ENABLED,
    STT_VAD_END_SILENCE_SECONDS,
    STT_VAD_MAX_UTTERANCE_SECONDS,
    STT_VAD_MIN_SPEECH_SECONDS,
    STT_VAD_RMS_THRESHOLD,
    STT_VOICE_SESSION_TIMEOUT_SECONDS,
    STT_WAKE_WORDS,
    STT_WORKERS,
)


@dataclass(frozen=True, slots=True)
class STTSettings:
    enabled: bool
    provider: str
    model: str
    language: str
    vad_enabled: bool
    min_speech_seconds: float
    end_silence_seconds: float
    max_utterance_seconds: float
    vad_rms_threshold: int
    voice_session_timeout_seconds: float
    wake_words: tuple[str, ...]
    queue_size: int
    workers: int
    log_transcript: bool
    save_audio: bool
    listen_mode: str


def validate_settings(settings: STTSettings) -> STTSettings:
    if settings.provider != "faster_whisper":
        raise ValueError("Provider STT yang tersedia hanya 'faster_whisper'.")
    if not settings.model.strip():
        raise ValueError("Model STT tidak boleh kosong.")
    if not settings.language.strip():
        raise ValueError("Language STT tidak boleh kosong.")
    if settings.min_speech_seconds <= 0:
        raise ValueError("Minimum speech harus lebih besar dari nol.")
    if settings.end_silence_seconds <= 0:
        raise ValueError("End silence harus lebih besar dari nol.")
    if settings.max_utterance_seconds <= settings.min_speech_seconds:
        raise ValueError("Maximum utterance harus lebih besar dari minimum speech.")
    if settings.vad_rms_threshold <= 0:
        raise ValueError("VAD RMS threshold harus lebih besar dari nol.")
    if settings.voice_session_timeout_seconds <= 0:
        raise ValueError("Voice session timeout harus lebih besar dari nol.")
    if not settings.wake_words or any(not word.strip() for word in settings.wake_words):
        raise ValueError("Wake words harus berisi minimal satu teks tidak kosong.")
    if settings.queue_size <= 0:
        raise ValueError("Ukuran STT queue harus lebih besar dari nol.")
    if settings.workers <= 0:
        raise ValueError("Jumlah STT worker harus lebih besar dari nol.")
    if settings.listen_mode not in {"wake_word", "always_active", "test_only"}:
        raise ValueError(
            "Listen mode harus wake_word, always_active, atau test_only."
        )
    if settings.save_audio:
        raise ValueError("Penyimpanan audio belum diaktifkan demi privasi.")
    return settings


def load_settings(path: Path, initial: STTSettings) -> STTSettings:
    if not path.exists():
        save_settings(path, initial)
        return validate_settings(initial)
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Pengaturan STT gagal dibaca: path={path.resolve()}, "
            f"error={type(error).__name__}: {error}"
        ) from error
    if not isinstance(parsed, dict):
        raise ValueError(f"Root pengaturan STT harus object: {path.resolve()}")
    return validate_settings(
        STTSettings(
            enabled=_boolean(parsed, "enabled", path),
            provider=_string(parsed, "provider", path),
            model=_string(parsed, "model", path),
            language=_string(parsed, "language", path),
            vad_enabled=_boolean(parsed, "vad_enabled", path),
            min_speech_seconds=_number(parsed, "min_speech_seconds", path),
            end_silence_seconds=_number(parsed, "end_silence_seconds", path),
            max_utterance_seconds=_number(parsed, "max_utterance_seconds", path),
            vad_rms_threshold=_integer(parsed, "vad_rms_threshold", path),
            voice_session_timeout_seconds=_number(
                parsed, "voice_session_timeout_seconds", path
            ),
            wake_words=_strings(parsed, "wake_words", path),
            queue_size=_integer(parsed, "queue_size", path),
            workers=_integer(parsed, "workers", path),
            log_transcript=_boolean(parsed, "log_transcript", path),
            save_audio=_boolean(parsed, "save_audio", path),
            listen_mode=_string(parsed, "listen_mode", path),
        )
    )


def save_settings(path: Path, settings: STTSettings) -> None:
    validated: STTSettings = validate_settings(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(validated), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_configured_settings() -> STTSettings:
    initial: STTSettings = STTSettings(
        enabled=False,
        provider=STT_PROVIDER,
        model=STT_MODEL,
        language=STT_LANGUAGE,
        vad_enabled=STT_VAD_ENABLED,
        min_speech_seconds=STT_VAD_MIN_SPEECH_SECONDS,
        end_silence_seconds=STT_VAD_END_SILENCE_SECONDS,
        max_utterance_seconds=STT_VAD_MAX_UTTERANCE_SECONDS,
        vad_rms_threshold=STT_VAD_RMS_THRESHOLD,
        voice_session_timeout_seconds=STT_VOICE_SESSION_TIMEOUT_SECONDS,
        wake_words=STT_WAKE_WORDS,
        queue_size=STT_QUEUE_SIZE,
        workers=STT_WORKERS,
        log_transcript=False,
        save_audio=False,
        listen_mode="wake_word",
    )
    return load_settings(STT_SETTINGS_FILE, initial)


def _string(data: dict[str, object], field: str, path: Path) -> str:
    value: object = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field STT '{field}' harus string tidak kosong: {path.resolve()}")
    return value.strip()


def _boolean(data: dict[str, object], field: str, path: Path) -> bool:
    value: object = data.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"Field STT '{field}' harus boolean: {path.resolve()}")
    return value


def _integer(data: dict[str, object], field: str, path: Path) -> int:
    value: object = data.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Field STT '{field}' harus integer: {path.resolve()}")
    return value


def _number(data: dict[str, object], field: str, path: Path) -> float:
    value: object = data.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Field STT '{field}' harus angka: {path.resolve()}")
    return float(value)


def _strings(data: dict[str, object], field: str, path: Path) -> tuple[str, ...]:
    value: object = data.get(field)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"Field STT '{field}' harus array string: {path.resolve()}")
    return tuple(item.strip().casefold() for item in value)
