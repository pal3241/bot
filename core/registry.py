from collections.abc import Awaitable, Callable

from core.context import AppContext


Feature = Callable[[AppContext], Awaitable[None]]
FEATURES: dict[str, Feature] = {}


def feature(name: str) -> Callable[[Feature], Feature]:
    if not name.strip():
        raise ValueError("Nama fitur tidak boleh kosong.")

    def decorator(function: Feature) -> Feature:
        if name in FEATURES:
            raise ValueError(f"Fitur dengan nama '{name}' sudah terdaftar.")
        FEATURES[name] = function
        return function

    return decorator

