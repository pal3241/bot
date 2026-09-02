import json
from dataclasses import asdict, dataclass
from pathlib import Path

from voice.converters.settings import VoiceConverterSettings


@dataclass(frozen=True)
class VoicePreferences:
    provider_name: str
    language: str
    converter: VoiceConverterSettings


def load_preferences(path: Path, initial: VoicePreferences) -> VoicePreferences:
    if not path.exists():
        save_preferences(path, initial)
        return initial
    if not path.is_file():
        raise ValueError(f"Path pengaturan voice bukan file: {path.resolve()}")

    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"JSON pengaturan voice tidak valid: path={path.resolve()}, "
            f"baris={error.lineno}, kolom={error.colno}, detail={error.msg}"
        ) from error
    return parse_preferences(parsed, path)


def save_preferences(path: Path, preferences: VoicePreferences) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path = path.with_suffix(path.suffix + ".tmp")
    serialized: str = json.dumps(
        asdict(preferences),
        ensure_ascii=False,
        indent=2,
    )
    temporary.write_text(serialized + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_preferences(value: object, path: Path) -> VoicePreferences:
    root: dict[str, object] = require_object(value, "root", path)
    provider_name: str = require_string(root, "provider_name", path)
    language: str = require_string(root, "language", path)
    converter_data: dict[str, object] = require_object(
        root.get("converter"),
        "converter",
        path,
    )
    return VoicePreferences(
        provider_name=provider_name,
        language=language,
        converter=VoiceConverterSettings(
            enabled=require_bool(converter_data, "enabled", path),
            converter=require_string(converter_data, "converter", path),
            model=require_optional_string(converter_data, "model", path),
            pitch=require_int(converter_data, "pitch", path),
            index_ratio=require_float(converter_data, "index_ratio", path),
            protect=require_float(converter_data, "protect", path),
        ),
    )


def require_object(value: object, field: str, path: Path) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(
            f"Field '{field}' pada pengaturan voice harus berupa object: {path.resolve()}"
        )
    return value


def require_string(data: dict[str, object], field: str, path: Path) -> str:
    value: object = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Field '{field}' pada pengaturan voice harus berupa string yang tidak kosong: "
            f"{path.resolve()}"
        )
    return value


def require_optional_string(
    data: dict[str, object],
    field: str,
    path: Path,
) -> str | None:
    value: object = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Field '{field}' pada pengaturan voice harus null atau string tidak kosong: "
            f"{path.resolve()}"
        )
    return value


def require_bool(data: dict[str, object], field: str, path: Path) -> bool:
    value: object = data.get(field)
    if not isinstance(value, bool):
        raise ValueError(
            f"Field '{field}' pada pengaturan voice harus berupa boolean: {path.resolve()}"
        )
    return value


def require_int(data: dict[str, object], field: str, path: Path) -> int:
    value: object = data.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(
            f"Field '{field}' pada pengaturan voice harus berupa integer: {path.resolve()}"
        )
    return value


def require_float(data: dict[str, object], field: str, path: Path) -> float:
    value: object = data.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(
            f"Field '{field}' pada pengaturan voice harus berupa angka: {path.resolve()}"
        )
    return float(value)

