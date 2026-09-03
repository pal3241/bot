from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord

from actions.models import ActionRequest, ActionResult, ActionRisk


@dataclass(frozen=True, slots=True)
class ActionContext:
    client: discord.Client
    message: discord.Message
    is_owner: bool


ActionHandler = Callable[[ActionContext, ActionRequest], Awaitable[ActionResult]]


@dataclass(frozen=True, slots=True)
class ActionSpec:
    name: str
    description: str
    risk: ActionRisk
    handler: ActionHandler


class ActionRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ActionSpec] = {}

    def register(self, spec: ActionSpec) -> None:
        name = spec.name.strip().casefold()
        if not name:
            raise ValueError("Action tool name tidak boleh kosong.")
        if name in self._tools:
            raise ValueError(f"Action tool sudah terdaftar: {name}")
        self._tools[name] = ActionSpec(name, spec.description, spec.risk, spec.handler)

    def get(self, name: str) -> ActionSpec | None:
        return self._tools.get(name.strip().casefold())

    def prompt_catalog(self) -> str:
        return "\n".join(
            f"- {spec.name}: {spec.description} [risk={spec.risk.value}]"
            for spec in self._tools.values()
        )

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)
