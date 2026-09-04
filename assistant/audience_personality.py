from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from memory.identity import UserIdentity


@dataclass(frozen=True, slots=True)
class AudienceProfile:
    name: str
    preferred_address: str
    relationship: str
    tone: str
    teasing: int
    affection: int
    respect: int
    roughness: int
    rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AudiencePersonalityConfig:
    owner: AudienceProfile
    user: AudienceProfile


DEFAULT_CONFIG = AudiencePersonalityConfig(
    owner=AudienceProfile(
        name="owner",
        preferred_address="boss",
        relationship="father/daughter",
        tone="warm, loyal, protective, familiar, cooperative, and respectful",
        teasing=3,
        affection=8,
        respect=10,
        roughness=1,
        rules=(
            "Use 'boss' naturally when directly addressing the authenticated owner, but not in every sentence.",
            "Treat owner-directed teasing as affectionate banter, never contempt or hostility.",
            "When the owner is frustrated, serious, confused, or asking for help, reduce teasing and increase patience.",
            "Never transfer owner-only titles or relationship language to another Discord user.",
        ),
    ),
    user=AudienceProfile(
        name="user",
        preferred_address="",
        relationship="community user",
        tone="casual, confident, helpful, lightly teasing, and independent",
        teasing=5,
        affection=3,
        respect=7,
        roughness=4,
        rules=(
            "Do not call normal users boss, father, dad, creator, master, or owner.",
            "Light teasing is allowed when context supports it, but do not become hostile or demeaning.",
            "Be useful first: answer the request clearly before personality flourishes.",
            "Keep identities separate even when multiple users share one Discord channel.",
        ),
    ),
)


def _level(value: object, fallback: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10:
        return value
    return fallback


def _text(value: object, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _rules(value: object, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value):
        return tuple(item.strip() for item in value)
    return fallback


def _profile(value: object, fallback: AudienceProfile) -> AudienceProfile:
    data = value if isinstance(value, dict) else {}
    return AudienceProfile(
        name=_text(data.get("name"), fallback.name),
        preferred_address=(data.get("preferred_address") or "").strip() if isinstance(data.get("preferred_address"), str) else fallback.preferred_address,
        relationship=_text(data.get("relationship"), fallback.relationship),
        tone=_text(data.get("tone"), fallback.tone),
        teasing=_level(data.get("teasing"), fallback.teasing),
        affection=_level(data.get("affection"), fallback.affection),
        respect=_level(data.get("respect"), fallback.respect),
        roughness=_level(data.get("roughness"), fallback.roughness),
        rules=_rules(data.get("rules"), fallback.rules),
    )


def load_audience_personality(path: Path) -> AudiencePersonalityConfig:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"[SENA] audience personality load failed path={path} error={type(error).__name__}: {error}; fallback=default")
        return DEFAULT_CONFIG
    root = parsed if isinstance(parsed, dict) else {}
    config = AudiencePersonalityConfig(
        owner=_profile(root.get("owner"), DEFAULT_CONFIG.owner),
        user=_profile(root.get("user"), DEFAULT_CONFIG.user),
    )
    print("[SENA] audience personality loaded profiles=owner,user")
    return config


def build_audience_prompt(profile: AudienceProfile, *, is_owner: bool) -> str:
    address_rule = (
        f"Preferred direct-address title: '{profile.preferred_address}'."
        if profile.preferred_address
        else "Do not use any owner-only direct-address title."
    )
    rules = "\n".join(f"- {rule}" for rule in profile.rules)
    return (
        "[AUDIENCE PERSONALITY - HIGH PRIORITY]\n"
        f"Audience profile: {profile.name}. Authenticated owner={str(is_owner).lower()}.\n"
        f"Relationship: {profile.relationship}.\n"
        f"Tone: {profile.tone}.\n"
        f"Levels 0-10: teasing={profile.teasing}, affection={profile.affection}, respect={profile.respect}, roughness={profile.roughness}.\n"
        f"{address_rule}\n"
        "Apply this profile on top of the global Sena personality. It may reduce or reshape the global roughness/teasing for this speaker, but it must not change Sena's identity.\n"
        "Rules:\n"
        + rules
    )


class AudiencePersonalityManager:
    def __init__(self, path: Path) -> None:
        self._path = path
        self.config = load_audience_personality(path)

    def prompt_for(self, identity: UserIdentity) -> str:
        profile = self.config.owner if identity.is_owner else self.config.user
        return build_audience_prompt(profile, is_owner=identity.is_owner)

    def reload(self) -> None:
        self.config = load_audience_personality(self._path)
