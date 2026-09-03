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


def format_history(
    entries: list[ConversationEntry],
    max_chars: int | None = None,
) -> str:
    if not entries:
        return ""
    if max_chars is not None and max_chars <= 0:
        raise ValueError("max_chars history harus lebih besar dari nol.")

    formatted: list[str] = [format_entry(entry) for entry in entries]
    if max_chars is not None:
        selected_reversed: list[str] = []
        used: int = 0
        for block in reversed(formatted):
            cost: int = len(block) + (2 if selected_reversed else 0)
            if selected_reversed and used + cost > max_chars:
                break
            if not selected_reversed and len(block) > max_chars:
                # Keep the newest message tail instead of sending an oversized prompt.
                block = block[-max_chars:]
                cost = len(block)
            selected_reversed.append(block)
            used += cost
        formatted = list(reversed(selected_reversed))

    if not formatted:
        return ""
    return "[Recent channel conversation]\n\n" + "\n\n".join(formatted)


def format_current_speaker(user_id: int, display_name: str, text: str) -> str:
    return (
        f"[Current speaker]\n{display_name} | id={user_id}\n\n"
        f"[Current message]\n{text}"
    )
