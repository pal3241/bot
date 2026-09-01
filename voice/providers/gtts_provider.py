import asyncio
import uuid
from pathlib import Path

from gtts import gTTS
from gtts.tts import gTTSError

from config import TTS_RETRY_COUNT, TTS_RETRY_DELAY_SECONDS
from voice.providers.base import TTSProvider


class GTTSProvider(TTSProvider):
    name: str = "gtts"

    def __init__(self) -> None:
        self.temp_folder: Path = Path("temp/tts")
        self.temp_folder.mkdir(parents=True, exist_ok=True)

    async def synthesize(self, text: str, language: str) -> Path:
        if not text.strip():
            raise ValueError("Teks TTS tidak boleh kosong.")
        if not language.strip():
            raise ValueError("Kode bahasa TTS tidak boleh kosong.")

        output: Path = self.temp_folder / f"{uuid.uuid4().hex}.mp3"
        for percobaan in range(1, TTS_RETRY_COUNT + 1):
            try:
                await asyncio.to_thread(self._generate, text, language, output)
                return output
            except (gTTSError, OSError) as error:
                if percobaan == TTS_RETRY_COUNT:
                    raise RuntimeError(
                        f"gTTS gagal setelah {TTS_RETRY_COUNT} percobaan: {error}"
                    ) from error
                print(
                    "PERINGATAN: gTTS gagal; "
                    f"percobaan={percobaan}, bahasa={language}, detail={error}"
                )
                await asyncio.sleep(TTS_RETRY_DELAY_SECONDS)

        raise RuntimeError("Proses sintesis gTTS berhenti tanpa menghasilkan audio.")

    def _generate(self, text: str, language: str, output: Path) -> None:
        tts: gTTS = gTTS(text=text, lang=language)
        tts.save(str(output))

