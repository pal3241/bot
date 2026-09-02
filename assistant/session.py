import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

from assistant.llm.base import ChatMessage


class SessionState(Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    SILENCED = "silenced"


@dataclass(frozen=True, slots=True)
class SessionKey:
    guild_id: int | None
    channel_id: int
    user_id: int


@dataclass(slots=True)
class ChatSession:
    state: SessionState = SessionState.INACTIVE
    history: list[ChatMessage] = field(default_factory=list)
    last_activity: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionManager:
    def __init__(self, timeout_seconds: float, history_max_messages: int) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Timeout session Sena harus lebih besar dari nol.")
        if history_max_messages <= 0:
            raise ValueError("Batas history Sena harus lebih besar dari nol.")
        self._timeout_seconds: float = timeout_seconds
        self._history_max_messages: int = history_max_messages
        self._sessions: dict[SessionKey, ChatSession] = {}

    def get(self, key: SessionKey) -> ChatSession:
        session: ChatSession | None = self._sessions.get(key)
        if session is None:
            session = ChatSession()
            self._sessions[key] = session
        return session

    def state(self, key: SessionKey) -> SessionState:
        session: ChatSession = self.get(key)
        if (
            session.state is SessionState.ACTIVE
            and time.monotonic() - session.last_activity >= self._timeout_seconds
        ):
            session.state = SessionState.INACTIVE
            session.history.clear()
            print(f"[SENA] session timeout user={key.user_id} channel={key.channel_id}")
        return session.state

    def activate(self, key: SessionKey) -> None:
        session: ChatSession = self.get(key)
        session.state = SessionState.ACTIVE
        session.last_activity = time.monotonic()
        print(f"[SENA] session activated user={key.user_id} channel={key.channel_id}")

    def silence(self, key: SessionKey) -> None:
        session: ChatSession = self.get(key)
        session.state = SessionState.SILENCED
        session.history.clear()
        print(f"[SENA] session silenced user={key.user_id} channel={key.channel_id}")

    def touch(self, session: ChatSession) -> None:
        session.last_activity = time.monotonic()

    def add_history(self, session: ChatSession, messages: list[ChatMessage]) -> None:
        session.history.extend(messages)
        if len(session.history) > self._history_max_messages:
            del session.history[: -self._history_max_messages]

    def clear(self) -> None:
        self._sessions.clear()
