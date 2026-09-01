import asyncio
import shutil
import uuid
from pathlib import Path

from voice.converters.base import VoiceConverter


class PassthroughConverter(VoiceConverter):
    name: str = "passthrough"

    def __init__(self) -> None:
        self.temp_folder: Path = Path("temp/converter")
        self.temp_folder.mkdir(parents=True, exist_ok=True)

    async def convert(self, input_audio: Path) -> Path:
        if not input_audio.is_file():
            raise FileNotFoundError(f"Audio input converter tidak ditemukan: {input_audio}")
        if input_audio.stat().st_size == 0:
            raise ValueError(f"Audio input converter kosong: {input_audio}")
        output: Path = self.temp_folder / f"{uuid.uuid4().hex}{input_audio.suffix}"
        await asyncio.to_thread(shutil.copyfile, input_audio, output)
        if output.stat().st_size == 0:
            raise RuntimeError(f"Converter menghasilkan file kosong: {output}")
        return output

