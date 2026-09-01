import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class RVCModel:
    name: str
    folder: Path
    weight_file: Path
    index_file: Path | None


def validate_model_name(name: str) -> str:
    normalized: str = name.strip()
    if not normalized or normalized in {".", ".."}:
        raise ValueError("Nama model tidak valid.")
    if any(character in normalized for character in '<>:"/\\|?*'):
        raise ValueError(f"Nama model mengandung karakter terlarang: '{name}'.")
    return normalized


def list_models(root: Path) -> list[RVCModel]:
    root.mkdir(parents=True, exist_ok=True)
    models: list[RVCModel] = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        weights: list[Path] = sorted(folder.glob("*.pth"))
        if len(weights) != 1:
            continue
        indexes: list[Path] = sorted(folder.glob("*.index"))
        if len(indexes) > 1:
            raise ValueError(f"Model '{folder.name}' memiliki lebih dari satu file .index.")
        models.append(
            RVCModel(
                name=folder.name,
                folder=folder,
                weight_file=weights[0],
                index_file=indexes[0] if indexes else None,
            )
        )
    return models


def get_model(root: Path, name: str) -> RVCModel:
    normalized: str = validate_model_name(name)
    matches: list[RVCModel] = [model for model in list_models(root) if model.name == normalized]
    if not matches:
        raise FileNotFoundError(f"Model RVC tidak ditemukan: '{normalized}'.")
    return matches[0]


def import_model(source: Path, root: Path, name: str) -> RVCModel:
    normalized: str = validate_model_name(name)
    if not source.is_file():
        raise FileNotFoundError(f"File model tidak ditemukan: {source}")
    target: Path = root / normalized
    if target.exists():
        raise FileExistsError(f"Model RVC sudah ada: '{normalized}'.")
    target.mkdir(parents=True)
    try:
        if source.suffix.lower() == ".zip":
            _import_zip(source, target)
        elif source.suffix.lower() == ".pth":
            shutil.copy2(source, target / source.name)
            indexes: list[Path] = sorted(source.parent.glob("*.index"))
            if len(indexes) == 1:
                shutil.copy2(indexes[0], target / indexes[0].name)
        else:
            raise ValueError("Import model hanya menerima file .zip atau .pth.")
        return get_model(root, normalized)
    except Exception:
        shutil.rmtree(target)
        raise


def delete_model(root: Path, name: str) -> None:
    model: RVCModel = get_model(root, name)
    resolved_root: Path = root.resolve()
    resolved_folder: Path = model.folder.resolve()
    if resolved_folder.parent != resolved_root:
        raise ValueError(f"Folder model berada di luar root yang diizinkan: {resolved_folder}")
    shutil.rmtree(resolved_folder)


def _import_zip(source: Path, target: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        candidates: list[zipfile.ZipInfo] = []
        for entry in archive.infolist():
            path: PurePosixPath = PurePosixPath(entry.filename)
            if entry.is_dir():
                continue
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"ZIP mengandung path tidak aman: '{entry.filename}'.")
            if path.suffix.lower() in {".pth", ".index"}:
                candidates.append(entry)
        weights: list[zipfile.ZipInfo] = [item for item in candidates if item.filename.lower().endswith(".pth")]
        indexes: list[zipfile.ZipInfo] = [item for item in candidates if item.filename.lower().endswith(".index")]
        if len(weights) != 1:
            raise ValueError(f"ZIP harus berisi tepat satu file .pth; ditemukan {len(weights)}.")
        if len(indexes) > 1:
            raise ValueError(f"ZIP maksimal berisi satu file .index; ditemukan {len(indexes)}.")
        for entry in weights + indexes:
            output: Path = target / PurePosixPath(entry.filename).name
            with archive.open(entry) as input_stream, output.open("wb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream)

