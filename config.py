from pathlib import Path


GIF_FOLDER: Path = Path(r"D:\import")
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
RVC_BASE_URL: str = "http://127.0.0.1:18000"
RVC_REQUEST_TIMEOUT_SECONDS: float = 120.0
RVC_CONFIG_TIMEOUT_SECONDS: float = 10.0
RVC_CHUNK_SECONDS: float = 0.5
W_OKADA_FOLDER: Path = Path("dist")
VOICE_SETTINGS_FILE: Path = Path("data/voice_settings.json")
AI_SETTINGS_FILE: Path = Path("data/ai_settings.json")
TTS_READY_QUEUE_SIZE: int = 2
LLM_PROVIDER: str = "openrouter"
OPENROUTER_MODEL: str = "openai/gpt-4o-mini"
NVIDIA_NIM_MODEL: str = "meta/llama-3.1-8b-instruct"
NVIDIA_NIM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
LLM_REQUEST_TIMEOUT_SECONDS: float = 60.0
LLM_MAX_TOKENS: int = 30
LLM_RETRY_COUNT: int = 2
LLM_RETRY_DELAY_SECONDS: float = 1.0
SENA_CHAT_TIMEOUT_SECONDS: float = 120.0
SENA_HISTORY_MAX_MESSAGES: int = 20
SENA_PERSONALITY_FILE: Path = Path("data/personality.txt")
SENA_LANGUAGE_MODE: str = "auto"
SENA_LANGUAGE: str = "id"
