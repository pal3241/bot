from collections.abc import Callable

from voice.converters.base import VoiceConverter
from voice.converters.passthrough_converter import PassthroughConverter
from voice.converters.rvc_converter import RVCConverter
from voice.converters.settings import VoiceConverterSettings


ConverterFactory = Callable[[VoiceConverterSettings], VoiceConverter]


def create_passthrough(settings: VoiceConverterSettings) -> VoiceConverter:
    return PassthroughConverter()


CONVERTERS: dict[str, ConverterFactory] = {
    "passthrough": create_passthrough,
    "rvc": RVCConverter,
}


def create_converter(name: str, settings: VoiceConverterSettings) -> VoiceConverter:
    normalized_name: str = name.strip().lower()
    factory: ConverterFactory | None = CONVERTERS.get(normalized_name)
    if factory is None:
        tersedia: str = ", ".join(CONVERTERS)
        raise ValueError(
            f"Voice converter tidak ditemukan: '{name}'. Converter tersedia: {tersedia}."
        )
    return factory(settings)


def register_converter(name: str, factory: ConverterFactory) -> None:
    normalized_name: str = name.strip().lower()
    if not normalized_name:
        raise ValueError("Nama voice converter tidak boleh kosong.")
    if normalized_name in CONVERTERS:
        raise ValueError(f"Voice converter '{normalized_name}' sudah terdaftar.")
    CONVERTERS[normalized_name] = factory

