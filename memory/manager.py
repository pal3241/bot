from memory.identity import UserIdentity
from memory.models import MemoryActionType, MemoryCandidate, MemoryRecord
from memory.normalization import lexical_similarity, normalize_memory_text
from memory.policy import MemoryPolicy, MemoryPolicyResult
from memory.retriever import select_memories
from memory.store import MemoryStore


class MemoryManager:
    def __init__(
        self,
        store: MemoryStore,
        policy: MemoryPolicy,
        retrieval_limit: int,
        context_max_chars: int,
    ) -> None:
        self._store: MemoryStore = store
        self._policy: MemoryPolicy = policy
        self._retrieval_limit: int = retrieval_limit
        self._context_max_chars: int = context_max_chars
        self.available: bool = False

    async def initialize(self) -> None:
        await self._store.initialize()
        self.available = True

    async def retrieve(
        self, identity: UserIdentity, query: str
    ) -> list[MemoryRecord]:
        if not identity.is_owner or not self.available:
            return []
        records: list[MemoryRecord] = await self._store.list_active(identity.user_id)
        selected: list[MemoryRecord] = select_memories(
            records, query, self._retrieval_limit, self._context_max_chars
        )
        await self._store.touch_access(
            identity.user_id, [record.id for record in selected]
        )
        return selected

    async def apply_action(
        self,
        identity: UserIdentity,
        candidate: MemoryCandidate,
        source: str,
    ) -> MemoryRecord | None:
        if not self.available:
            return None
        policy_result: MemoryPolicyResult = self._policy.validate(identity, candidate)
        if not policy_result.allowed:
            print(
                f"[SENA MEMORY] action rejected action={candidate.action.value} "
                f"reason={policy_result.reason}"
            )
            return None
        if candidate.action is MemoryActionType.DELETE:
            target_id: int | None = candidate.target_memory_id
            if target_id is None and candidate.content is not None:
                active: list[MemoryRecord] = await self._store.list_active(
                    identity.user_id
                )
                matches: list[tuple[float, MemoryRecord]] = sorted(
                    (
                        (lexical_similarity(record.content, candidate.content), record)
                        for record in active
                    ),
                    key=lambda item: item[0],
                    reverse=True,
                )
                if matches and matches[0][0] >= 0.2:
                    target_id = matches[0][1].id
            if target_id is None:
                return None
            await self._store.soft_delete(identity.user_id, target_id)
            return None
        active: list[MemoryRecord] = await self._store.list_active(identity.user_id)
        if candidate.content is None:
            return None
        normalized: str = normalize_memory_text(candidate.content)
        exact: MemoryRecord | None = next(
            (record for record in active if record.normalized_content == normalized), None
        )
        if exact is not None and candidate.action is MemoryActionType.STORE:
            return exact
        target_id = candidate.target_memory_id
        if target_id is None:
            related: list[tuple[float, MemoryRecord]] = sorted(
                (
                    (lexical_similarity(record.content, candidate.content), record)
                    for record in active
                    if record.category == candidate.category
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            if related and related[0][0] >= 0.5:
                target_id = related[0][1].id
        if candidate.action is MemoryActionType.UPDATE or target_id is not None:
            if target_id is None:
                return None
            return await self._store.update(
                identity.user_id, target_id, candidate, source
            )
        return await self._store.insert(identity.user_id, candidate, source)

    async def list_memories(self, owner_id: int) -> list[MemoryRecord]:
        if not self.available:
            return []
        return await self._store.list_active(owner_id)

    async def count_active(self, owner_id: int) -> int:
        if not self.available:
            return 0
        return await self._store.count_active(owner_id)

    async def close(self) -> None:
        await self._store.close()
        self.available = False
