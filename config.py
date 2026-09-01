from pathlib import Path


GIF_FOLDER: Path = Path(r"D:\Discord GIF")
MAX_EMOJI_SIZE: int = 256 * 1024
TTS_PROVIDER: str = "gtts"
TTS_LANGUAGE: str = "id"
TTS_RETRY_COUNT: int = 3
TTS_RETRY_DELAY_SECONDS: float = 1.0
VOICE_CONVERTER_ENABLED: bool = False
VOICE_CONVERTER: str = "passthrough"
VOICE_CONVERTER_PITCH: int = 0
VOICE_CONVERTER_INDEX_RATIO: float = 0.5
VOICE_CONVERTER_PROTECT: float = 0.5
RVC_MODELS_FOLDER: Path = Path("models/rvc")
