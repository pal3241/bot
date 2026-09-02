from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserIdentity:
    user_id: int
    display_name: str
    is_owner: bool
    relationship: str | None
    sena_role: str | None


def parse_owner_id(raw_value: str | None) -> int | None:
    if raw_value is None or not raw_value.strip():
        return None
    normalized: str = raw_value.strip()
    if not normalized.isdecimal():
        return None
    owner_id: int = int(normalized)
    return owner_id if owner_id > 0 else None


class OwnerResolver:
    def __init__(self, owner_id: int | None) -> None:
        self.owner_id: int | None = owner_id

    def resolve(self, user_id: int, display_name: str) -> UserIdentity:
        clean_name: str = display_name.strip()
        if not clean_name:
            raise ValueError("Display name identity tidak boleh kosong.")
        is_owner: bool = self.owner_id is not None and user_id == self.owner_id
        return UserIdentity(
            user_id=user_id,
            display_name=clean_name,
            is_owner=is_owner,
            relationship="father" if is_owner else None,
            sena_role="daughter" if is_owner else None,
        )
