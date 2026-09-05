import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

from assistant.conversation import ConversationEntry, ConversationKey


class SessionState(Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    SILENCED = "silenced"


@dataclass(slots=True)
class ChatSession:
    state: SessionState = SessionState.INACTIVE
    history: list[ConversationEntry] = field(default_factory=list)
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
        self._sessions: dict[ConversationKey, ChatSession] = {}

    def get(self, key: ConversationKey) -> ChatSession:
        session: ChatSession | None = self._sessions.get(key)
        if session is None:
            session = ChatSession()
            self._sessions[key] = session
        return session

    def peek(self, key: ConversationKey) -> ChatSession | None:
        session: ChatSession | None = self._sessions.get(key)
        if session is None:
            return None
        if (
            session.state is SessionState.ACTIVE
            and time.monotonic() - session.last_activity >= self._timeout_seconds
        ):
            session.state = SessionState.INACTIVE
            session.history.clear()
            del self._sessions[key]
            print(
                f"[SENA] session timeout source={key.source} channel={key.channel_id}"
            )
            return None
        return session

    def state(self, key: ConversationKey) -> SessionState:
        session: ChatSession | None = self.peek(key)
        return SessionState.INACTIVE if session is None else session.state

    def activate(self, key: ConversationKey) -> ChatSession:
        session: ChatSession = self.get(key)
        session.state = SessionState.ACTIVE
        session.last_activity = time.monotonic()
        print(f"[SENA] session activated source={key.source} channel={key.channel_id}")
        return session

    def silence(self, key: ConversationKey) -> ChatSession:
        session: ChatSession = self.get(key)
        session.state = SessionState.SILENCED
        session.history.clear()
        session.last_activity = time.monotonic()
        print(f"[SENA] session silenced source={key.source} channel={key.channel_id}")
        return session

    def touch(self, session: ChatSession) -> None:
        session.last_activity = time.monotonic()

    def add_history(
        self, session: ChatSession, entries: list[ConversationEntry]
    ) -> None:
        session.history.extend(entries)
        if len(session.history) > self._history_max_messages:
            del session.history[: -self._history_max_messages]

    def clear_channel(
        self,
        *,
        source: str,
        guild_id: int | None,
        channel_id: int,
    ) -> int:
        keys = [
            key
            for key in self._sessions
            if key.source == source
            and key.guild_id == guild_id
            and key.channel_id == channel_id
        ]
        for key in keys:
            self._sessions[key].history.clear()
            del self._sessions[key]
        return len(keys)

    def clear(self) -> int:
        count = len(self._sessions)
        for session in self._sessions.values():
            session.history.clear()
        self._sessions.clear()
        return count
