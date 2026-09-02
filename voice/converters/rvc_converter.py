from pathlib import Path

from config import (
    RVC_BASE_URL,
    RVC_CHUNK_SECONDS,
    RVC_REQUEST_TIMEOUT_SECONDS,
    TTS_RETRY_COUNT,
    TTS_RETRY_DELAY_SECONDS,
    W_OKADA_FOLDER,
)
from voice.converters.base import VoiceConverter
from voice.converters.settings import VoiceConverterSettings
from voice.converters.w_okada_client import WOkadaClient, WOkadaModel
from voice.models import RVCModel


class RVCConverter(VoiceConverter):
    name: str = "rvc"

    def __init__(self, settings: VoiceConverterSettings) -> None:
        self.settings: VoiceConverterSettings = settings
        self.client: WOkadaClient = WOkadaClient(
            base_url=RVC_BASE_URL,
            timeout_seconds=RVC_REQUEST_TIMEOUT_SECONDS,
            chunk_seconds=RVC_CHUNK_SECONDS,
            retry_count=TTS_RETRY_COUNT,
            retry_delay_seconds=TTS_RETRY_DELAY_SECONDS,
        )

    async def convert(self, input_audio: Path) -> Path:
        if not input_audio.is_file():
            raise FileNotFoundError(f"Audio input RVC tidak ditemukan: {input_audio}")
        if input_audio.stat().st_size == 0:
            raise ValueError(f"Audio input RVC kosong: {input_audio}")
        return await self.client.convert(
            input_audio=input_audio,
            model=self.settings.model,
            pitch=self.settings.pitch,
            index_ratio=self.settings.index_ratio,
            protect=self.settings.protect,
        )

    async def list_models(self) -> list[WOkadaModel]:
        return await self.client.list_rvc_models()

    async def import_model(self, model: RVCModel) -> WOkadaModel:
        return await self.client.import_model(model, W_OKADA_FOLDER)
