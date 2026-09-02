from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConversationKey:
    source: str
    guild_id: int | None
    channel_id: int
    participant_id: int | None


@dataclass(frozen=True, slots=True)
class ConversationEntry:
    role: str
    content: str
    user_id: int | None
    display_name: str | None
    timestamp: float


def build_conversation_key(
    source: str,
    guild_id: int | None,
    channel_id: int,
    user_id: int,
) -> ConversationKey:
    participant_id: int | None = None if source == "discord_text" else user_id
    return ConversationKey(
        source=source,
        guild_id=guild_id,
        channel_id=channel_id,
        participant_id=participant_id,
    )


def format_entry(entry: ConversationEntry) -> str:
    if entry.role == "assistant":
        return f"[Sena]\n{entry.content}"
    name: str = entry.display_name or "Unknown user"
    identity: str = f"{name} | id={entry.user_id}"
    return f"[{identity}]\n{entry.content}"


def format_history(entries: list[ConversationEntry]) -> str:
    if not entries:
        return ""
    return "[Recent channel conversation]\n\n" + "\n\n".join(
        format_entry(entry) for entry in entries
    )


def format_current_speaker(user_id: int, display_name: str, text: str) -> str:
    return (
        f"[Current speaker]\n{display_name} | id={user_id}\n\n"
        f"[Current message]\n{text}"
    )
