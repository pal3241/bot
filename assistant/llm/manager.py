from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from assistant.llm.base import ChatMessage, LLMProvider, LLMProviderError
from assistant.llm.routing import ModelTarget, RoutingTier


AdvancedChat = Callable[..., Awaitable[str]]


class LLMManager:
    def __init__(
        self,
        provider: LLMProvider,
        provider_name: str,
        model: str,
        *,
        providers: dict[str, LLMProvider] | None = None,
        routes: dict[RoutingTier, ModelTarget] | None = None,
        fallback_targets: tuple[ModelTarget, ...] = (),
        tier_fallback_targets: dict[RoutingTier, tuple[ModelTarget, ...]] | None = None,
        tier_timeout_seconds: dict[RoutingTier, float] | None = None,
        json_prefill_enabled: bool = True,
        prompt_cache_enabled: bool = True,
    ) -> None:
        primary = ModelTarget(provider_name, model)
        provider_pool = dict(providers or {})
        provider_pool.setdefault(primary.provider_name, provider)

        self._providers: dict[str, LLMProvider] = provider_pool
        self._routes: dict[RoutingTier, ModelTarget] = {
            RoutingTier.FAST: primary,
            RoutingTier.STANDARD: primary,
            RoutingTier.COMPLEX: primary,
            **(routes or {}),
        }
        self._fallback_targets = fallback_targets
        self._tier_fallback_targets = dict(tier_fallback_targets or {})
        self._tier_timeout_seconds = dict(tier_timeout_seconds or {})
        self._json_prefill_enabled = json_prefill_enabled
        self._prompt_cache_enabled = prompt_cache_enabled
        self._provider_name = primary.provider_name
        self._model = primary.model
        print(
            f"[SENA ROUTER] fast={self._describe(RoutingTier.FAST)} "
            f"standard={self._describe(RoutingTier.STANDARD)} "
            f"complex={self._describe(RoutingTier.COMPLEX)} "
            f"fallbacks={','.join(self._target_label(item) for item in fallback_targets) or '-'}"
        )

    @staticmethod
    def _target_label(target: ModelTarget) -> str:
        return f"{target.provider_name}:{target.model}"

    def _describe(self, tier: RoutingTier) -> str:
        return self._target_label(self._routes[tier])

    def _candidates(self, tier: RoutingTier) -> tuple[ModelTarget, ...]:
        tier_fallbacks = self._tier_fallback_targets.get(tier, self._fallback_targets)
        ordered = (self._routes[tier], *tier_fallbacks)
        seen: set[tuple[str, str]] = set()
        result: list[ModelTarget] = []
        for target in ordered:
            if target.key in seen or target.provider_name not in self._providers:
                continue
            seen.add(target.key)
            result.append(target)
        return tuple(result)

    async def _chat_target(
        self,
        target: ModelTarget,
        messages: list[ChatMessage],
        *,
        json_prefill: bool,
        cache_key: str | None,
    ) -> str:
        provider = self._providers[target.provider_name]
        advanced: Any = getattr(provider, "chat_with_options", None)
        if callable(advanced):
            return await advanced(
                messages,
                target.model,
                assistant_prefill=(
                    "{"
                    if json_prefill
                    and self._json_prefill_enabled
                    and target.provider_name == "openrouter"
                    else None
                ),
                cache_key=cache_key if self._prompt_cache_enabled else None,
                json_object=json_prefill,
            )
        return await provider.chat(messages, target.model)

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tier: RoutingTier = RoutingTier.STANDARD,
        json_prefill: bool = False,
        cache_key: str | None = None,
    ) -> str:
        candidates = self._candidates(tier)
        if not candidates:
            raise LLMProviderError(f"Tidak ada model tersedia untuk route {tier.value}.")

        failures: list[str] = []
        route_started = asyncio.get_running_loop().time()
        route_timeout = self._tier_timeout_seconds.get(tier)
        for index, target in enumerate(candidates):
            try:
                print(
                    f"[SENA ROUTER] tier={tier.value} attempt={index + 1} "
                    f"target={self._target_label(target)}"
                )
                if route_timeout is None:
                    return await self._chat_target(
                        target,
                        messages,
                        json_prefill=json_prefill,
                        cache_key=cache_key,
                    )
                remaining = route_timeout - (
                    asyncio.get_running_loop().time() - route_started
                )
                if remaining <= 0:
                    break
                async with asyncio.timeout(remaining):
                    return await self._chat_target(
                        target,
                        messages,
                        json_prefill=json_prefill,
                        cache_key=cache_key,
                    )
            except TimeoutError:
                failures.append(
                    f"{self._target_label(target)}=deadline {route_timeout:g}s"
                )
                print(
                    f"[SENA ROUTER] deadline tier={tier.value} "
                    f"limit={route_timeout:g}s target={self._target_label(target)}"
                )
                break
            except LLMProviderError as error:
                failures.append(f"{self._target_label(target)}={error}")
                if index + 1 < len(candidates):
                    print(
                        f"[SENA ROUTER] fallback from={self._target_label(target)} "
                        f"to={self._target_label(candidates[index + 1])}"
                    )

        detail = " | ".join(failures) or "route deadline habis"
        raise LLMProviderError(f"Semua model route {tier.value} gagal: {detail}")

    async def close(self) -> None:
        unique = {id(provider): provider for provider in self._providers.values()}
        results = await asyncio.gather(
            *(provider.close() for provider in unique.values()),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                print(
                    f"[SENA ROUTER] provider close failed "
                    f"type={type(result).__name__} detail={result}"
                )
