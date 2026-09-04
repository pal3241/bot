from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from scheduler.models import ScheduledJob


ScheduledJobHandler = Callable[[ScheduledJob], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ScheduledJobSpec:
    name: str
    description: str
    handler: ScheduledJobHandler


class ScheduledJobRegistry:
    """Registry of job types that are safe to execute from the persistent scheduler.

    A feature must explicitly register a handler before its job type can be scheduled.
    This keeps the scheduler universal without allowing arbitrary action/tool execution.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, ScheduledJobSpec] = {}

    def register(
        self,
        name: str,
        description: str,
        handler: ScheduledJobHandler,
    ) -> None:
        normalized = name.strip().casefold()
        if not normalized or "." not in normalized:
            raise ValueError("Scheduled job type harus berbentuk namespace.name.")
        if normalized in self._jobs:
            raise ValueError(f"Scheduled job type sudah terdaftar: {normalized}")
        self._jobs[normalized] = ScheduledJobSpec(
            normalized,
            description.strip(),
            handler,
        )

    def has(self, name: str) -> bool:
        return name.strip().casefold() in self._jobs

    def get(self, name: str) -> ScheduledJobSpec | None:
        return self._jobs.get(name.strip().casefold())

    async def execute(self, job: ScheduledJob) -> None:
        spec = self.get(job.job_type)
        if spec is None:
            raise LookupError(f"Scheduled job type tidak tersedia: {job.job_type}")
        await spec.handler(job)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._jobs)

    def prompt_catalog(self) -> str:
        if not self._jobs:
            return "none"
        return "; ".join(
            f"{spec.name} ({spec.description})" for spec in self._jobs.values()
        )
