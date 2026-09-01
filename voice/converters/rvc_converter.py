from pathlib import Path

from config import RVC_MODELS_FOLDER
from voice.converters.base import VoiceConverter
from voice.converters.settings import VoiceConverterSettings
from voice.models import get_model


class RVCBackendNotConfiguredError(ConnectionError):
    pass


class RVCConverter(VoiceConverter):
    name: str = "rvc"

    def __init__(self, settings: VoiceConverterSettings) -> None:
        self.settings: VoiceConverterSettings = settings

    async def convert(self, input_audio: Path) -> Path:
        if not input_audio.is_file():
            raise FileNotFoundError(f"Audio input RVC tidak ditemukan: {input_audio}")
        if self.settings.model is None:
            raise ValueError("Model RVC belum dipilih.")
        get_model(RVC_MODELS_FOLDER, self.settings.model)
        raise RVCBackendNotConfiguredError(
            "Backend RVC belum dikonfigurasi. Pasang w-okada, lalu tentukan versi dan "
            "protokol API yang digunakan sebelum mengaktifkan converter 'rvc'."
        )
