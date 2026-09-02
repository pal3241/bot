import re
from dataclasses import dataclass
from enum import Enum

from assistant.session import SessionState


DIRECT_ADDRESS_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*(?:hey\s+)?(?:sen|sena|senna)\b[\s,:!?-]*", re.IGNORECASE
)
SILENCE_COMMANDS: frozenset[str] = frozenset(
    {"diam", "diam dulu", "tidur", "tidur dulu", "stop", "stop dulu", "mute", "shut up", "sleep"}
)
WAKE_COMMANDS: frozenset[str] = frozenset({"bangun", "wake", "unmute"})


class MessageAction(Enum):
    IGNORE = "ignore"
    CONTEXT_ONLY = "context_only"
    RESPOND = "respond"


class SessionCommand(Enum):
    SILENCE = "silence"
    WAKE = "wake"


@dataclass(frozen=True, slots=True)
class MessageDecision:
    action: MessageAction
    reason: str
    cleaned_text: str
    command: SessionCommand | None


@dataclass(frozen=True, slots=True)
class MessageFacts:
    author_is_bot: bool
    mentioned_bot: bool
    is_reply: bool
    reply_resolved: bool
    replied_to_bot: bool
    content: str
    session_state: SessionState


def remove_direct_address(content: str) -> tuple[str, bool]:
    match: re.Match[str] | None = DIRECT_ADDRESS_PATTERN.match(content)
    if match is None:
        return content.strip(), False
    return content[match.end() :].strip(), True


def detect_command(text: str) -> SessionCommand | None:
    normalized: str = text.strip().casefold()
    if normalized in SILENCE_COMMANDS:
        return SessionCommand.SILENCE
    if normalized in WAKE_COMMANDS:
        return SessionCommand.WAKE
    return None


def classify_message(facts: MessageFacts) -> MessageDecision:
    clean_text, direct_address = remove_direct_address(facts.content)
    command: SessionCommand | None = detect_command(clean_text)
    if facts.author_is_bot:
        return MessageDecision(MessageAction.IGNORE, "bot_author", clean_text, None)
    if facts.mentioned_bot:
        return MessageDecision(MessageAction.RESPOND, "explicit_mention", clean_text, command)
    if facts.is_reply and not facts.reply_resolved:
        return MessageDecision(MessageAction.IGNORE, "unresolved_reply", clean_text, None)
    if facts.replied_to_bot:
        return MessageDecision(MessageAction.RESPOND, "reply_to_bot", clean_text, command)
    if facts.is_reply:
        return MessageDecision(MessageAction.IGNORE, "reply_to_other", clean_text, None)
    if direct_address:
        return MessageDecision(MessageAction.RESPOND, "direct_address", clean_text, command)
    if facts.session_state is SessionState.ACTIVE:
        return MessageDecision(MessageAction.CONTEXT_ONLY, "active_context", clean_text, None)
    return MessageDecision(MessageAction.IGNORE, "inactive_session", clean_text, None)
