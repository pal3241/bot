from __future__ import annotations

from types import ModuleType
from typing import Any

from assistant.llm.routing import ModelTarget, RoutingTier
from assistant.settings import AISettings


def install_routing_runtime_policy(manager_module: ModuleType) -> None:
    """Make persisted/UI route choices authoritative at runtime.

    Older Routing V2 code treated NVIDIA NIM as categorically too slow for FAST
    and STANDARD and silently rewrote those targets to OpenRouter. That made the
    AI Settings UI misleading. This compatibility policy keeps the existing
    builder but removes that forced provider rewrite and makes tier deadlines
    provider-aware.
    """
    if getattr(manager_module, "_sena_explicit_route_policy_installed", False):
        return

    def respect_target(
        settings: AISettings,
        target: ModelTarget,
        tier: RoutingTier,
    ) -> ModelTarget:
        del settings, tier
        return target

    def configured_fallback(settings: AISettings) -> ModelTarget:
        primary = ModelTarget(
            settings.provider_name,
            manager_module._model_for_provider(settings, settings.provider_name),
        )
        return manager_module._route_target(
            settings,
            settings.fallback_provider,
            settings.fallback_model,
            primary,
        )

    manager_module._latency_safe_target = respect_target
    manager_module._openrouter_fallback = configured_fallback

    original_build = manager_module.build_llm_manager

    def build_with_provider_aware_deadlines(settings: AISettings) -> Any:
        llm = original_build(settings)
        for tier in (RoutingTier.FAST, RoutingTier.STANDARD):
            target = llm._routes[tier]
            if target.provider_name == "nvidia_nim":
                llm._tier_timeout_seconds[tier] = settings.request_timeout_seconds
        return llm

    manager_module.build_llm_manager = build_with_provider_aware_deadlines
    manager_module._sena_explicit_route_policy_installed = True
