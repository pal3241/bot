SUPPORTED_LANGUAGE_MODES: frozenset[str] = frozenset({"auto", "fixed"})


def build_language_prompt(mode: str, language: str) -> str:
    if mode not in SUPPORTED_LANGUAGE_MODES:
        raise ValueError(
            f"SENA_LANGUAGE_MODE '{mode}' tidak valid. Pilih salah satu: auto, fixed."
        )
    if mode == "fixed":
        if not language.strip():
            raise ValueError("SENA_LANGUAGE wajib diisi saat language mode=fixed.")
        return f"Always respond using language code '{language.strip()}'."
    return (
        "Respond naturally in the language used by the user's latest message. "
        "If the user mixes languages, you may mix them naturally too."
    )
