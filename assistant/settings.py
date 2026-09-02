import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AISettings:
    provider_name: str
    openrouter_model: str
    nvidia_nim_model: str
    nvidia_nim_base_url: str
    max_tokens: int
    request_timeout_seconds: float
    retry_count: int
    retry_delay_seconds: float
    chat_timeout_seconds: float
    history_max_messages: int


def validate_settings(settings: AISettings) -> AISettings:
    if settings.provider_name not in {"openrouter", "nvidia_nim"}:
        raise ValueError("Provider AI harus 'openrouter' atau 'nvidia_nim'.")
    if not settings.openrouter_model.strip():
        raise ValueError("Model OpenRouter tidak boleh kosong.")
    if not settings.nvidia_nim_model.strip():
        raise ValueError("Model NVIDIA NIM tidak boleh kosong.")
    if not settings.nvidia_nim_base_url.startswith(("http://", "https://")):
        raise ValueError("Base URL NVIDIA NIM harus diawali http:// atau https://.")
    if settings.max_tokens <= 0:
        raise ValueError("Maks token harus lebih besar dari nol.")
    if settings.request_timeout_seconds <= 0:
        raise ValueError("Request timeout harus lebih besar dari nol.")
    if settings.retry_count < 0:
        raise ValueError("Jumlah retry tidak boleh negatif.")
    if settings.retry_delay_seconds < 0:
        raise ValueError("Retry delay tidak boleh negatif.")
    if settings.chat_timeout_seconds <= 0:
        raise ValueError("Session timeout harus lebih besar dari nol.")
    if settings.history_max_messages <= 0:
        raise ValueError("Batas history harus lebih besar dari nol.")
    return settings


def load_settings(path: Path, initial: AISettings) -> AISettings:
    if not path.exists():
        save_settings(path, initial)
        return validate_settings(initial)
    if not path.is_file():
        raise ValueError(f"Path pengaturan AI bukan file: {path.resolve()}")
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"JSON pengaturan AI tidak valid: path={path.resolve()}, "
            f"baris={error.lineno}, kolom={error.colno}, detail={error.msg}"
        ) from error
    if not isinstance(parsed, dict):
        raise ValueError(f"Root pengaturan AI harus berupa object: {path.resolve()}")
    return validate_settings(
        AISettings(
            provider_name=_string(parsed, "provider_name", path),
            openrouter_model=_string(parsed, "openrouter_model", path),
            nvidia_nim_model=_string(parsed, "nvidia_nim_model", path),
            nvidia_nim_base_url=_string(parsed, "nvidia_nim_base_url", path),
            max_tokens=_integer(parsed, "max_tokens", path),
            request_timeout_seconds=_number(parsed, "request_timeout_seconds", path),
            retry_count=_integer(parsed, "retry_count", path),
            retry_delay_seconds=_number(parsed, "retry_delay_seconds", path),
            chat_timeout_seconds=_number(parsed, "chat_timeout_seconds", path),
            history_max_messages=_integer(parsed, "history_max_messages", path),
        )
    )


def save_settings(path: Path, settings: AISettings) -> None:
    validated: AISettings = validate_settings(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(validated), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _string(data: dict[str, object], field: str, path: Path) -> str:
    value: object = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Field '{field}' harus berupa string tidak kosong: {path.resolve()}"
        )
    return value.strip()


def _integer(data: dict[str, object], field: str, path: Path) -> int:
    value: object = data.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Field '{field}' harus berupa integer: {path.resolve()}")
    return value


def _number(data: dict[str, object], field: str, path: Path) -> float:
    value: object = data.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Field '{field}' harus berupa angka: {path.resolve()}")
    return float(value)
