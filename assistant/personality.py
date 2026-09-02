from pathlib import Path


class PersonalityFileError(RuntimeError):
    pass


class PersonalityManager:
    def __init__(self, path: Path) -> None:
        self._path: Path = path
        self._prompt: str = self._read()

    def _read(self) -> str:
        try:
            prompt: str = self._path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise PersonalityFileError(
                f"Personality Sena gagal dibaca dari '{self._path}': {error}"
            ) from error
        if not prompt:
            raise PersonalityFileError(f"Personality Sena di '{self._path}' kosong.")
        return prompt

    def load(self) -> str:
        return self._prompt

    def reload(self) -> None:
        self._prompt = self._read()
