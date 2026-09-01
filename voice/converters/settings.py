from dataclasses import dataclass, replace


@dataclass(frozen=True)
class VoiceConverterSettings:
    enabled: bool
    converter: str
    model: str | None
    pitch: int
    index_ratio: float
    protect: float

    def __post_init__(self) -> None:
        if not self.converter.strip():
            raise ValueError("Nama voice converter tidak boleh kosong.")
        if not -24 <= self.pitch <= 24:
            raise ValueError("Pitch harus berada di antara -24 dan +24 semitone.")
        if not 0.0 <= self.index_ratio <= 1.0:
            raise ValueError("Index ratio harus berada di antara 0.0 dan 1.0.")
        if not 0.0 <= self.protect <= 1.0:
            raise ValueError("Protect harus berada di antara 0.0 dan 1.0.")


def set_enabled(settings: VoiceConverterSettings, enabled: bool) -> VoiceConverterSettings:
    return replace(settings, enabled=enabled)


def set_converter(settings: VoiceConverterSettings, converter: str) -> VoiceConverterSettings:
    return replace(settings, converter=converter.strip().lower())


def set_model(settings: VoiceConverterSettings, model: str | None) -> VoiceConverterSettings:
    return replace(settings, model=model)


def set_pitch(settings: VoiceConverterSettings, pitch: int) -> VoiceConverterSettings:
    return replace(settings, pitch=pitch)


def set_index_ratio(settings: VoiceConverterSettings, index_ratio: float) -> VoiceConverterSettings:
    return replace(settings, index_ratio=index_ratio)


def set_protect(settings: VoiceConverterSettings, protect: float) -> VoiceConverterSettings:
    return replace(settings, protect=protect)

