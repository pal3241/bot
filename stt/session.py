import re
import time
from dataclasses import dataclass
from enum import Enum


class VoiceSessionState(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    SILENCED = "silenced"


@dataclass(frozen=True, slots=True)
class VoiceSessionKey:
    guild_id: int
    voice_channel_id: int
    user_id: int


@dataclass(slots=True)
class VoiceSession:
    state: VoiceSessionState
    last_activity: float


@dataclass(frozen=True, slots=True)
class VoiceRoute:
    prompt: str | None
    acknowledgement: str | None
    state: VoiceSessionState


class VoiceSessionRouter:
    def __init__(self, wake_words: tuple[str, ...], timeout_seconds: float) -> None:
        escaped: list[str] = sorted(
            (re.escape(word.strip()) for word in wake_words),
            key=len,
            reverse=True,
        )
        self._wake_pattern: re.Pattern[str] = re.compile(
            rf"(?:^|\b)(?:{'|'.join(escaped)})(?:\b|$)", re.IGNORECASE
        )
        self._timeout_seconds: float = timeout_seconds
        self._sessions: dict[VoiceSessionKey, VoiceSession] = {}
        self._sleep_commands: frozenset[str] = frozenset(
            {"diam", "tidur", "stop", "mute", "sleep", "shut up"}
        )

    def route(self, key: VoiceSessionKey, transcript: str, listen_mode: str) -> VoiceRoute:
        normalized: str = transcript.strip()
        if not normalized:
            raise ValueError("Transcript voice tidak boleh kosong.")
        session: VoiceSession = self._get(key)
        self._apply_timeout(session)
        wake_match: re.Match[str] | None = self._wake_pattern.search(normalized)
        command: str = normalized
        if wake_match is not None:
            without_wake: str = (
                normalized[: wake_match.start()] + normalized[wake_match.end() :]
            )
            command = re.sub(r"\s+", " ", without_wake).strip(" ,.!?;:")
            if command.casefold() in self._sleep_commands:
                session.state = VoiceSessionState.SILENCED
                session.last_activity = time.monotonic()
                return VoiceRoute(None, "oke, aku diam.", session.state)
            session.state = VoiceSessionState.ACTIVE
            session.last_activity = time.monotonic()
            if not command:
                return VoiceRoute(None, "iya?", session.state)
            return VoiceRoute(command, None, session.state)
        if listen_mode == "always_active":
            session.state = VoiceSessionState.ACTIVE
        if session.state is not VoiceSessionState.ACTIVE:
            return VoiceRoute(None, None, session.state)
        session.last_activity = time.monotonic()
        return VoiceRoute(normalized, None, session.state)

    def _get(self, key: VoiceSessionKey) -> VoiceSession:
        session: VoiceSession | None = self._sessions.get(key)
        if session is None:
            session = VoiceSession(VoiceSessionState.IDLE, time.monotonic())
            self._sessions[key] = session
        return session

    def _apply_timeout(self, session: VoiceSession) -> None:
        if (
            session.state is VoiceSessionState.ACTIVE
            and time.monotonic() - session.last_activity >= self._timeout_seconds
        ):
            session.state = VoiceSessionState.IDLE

    def clear(self) -> None:
        self._sessions.clear()

    @property
    def active_count(self) -> int:
        for session in self._sessions.values():
            self._apply_timeout(session)
        return sum(
            session.state is VoiceSessionState.ACTIVE
            for session in self._sessions.values()
        )
