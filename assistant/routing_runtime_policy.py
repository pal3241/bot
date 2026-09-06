from __future__ import annotations

import os
from types import ModuleType
from typing import Any

from assistant.llm.base import LLMConfigurationError, LLMProvider
from assistant.llm.manager import LLMManager
from assistant.llm.registry import create_provider
from assistant.llm.routing import ModelTarget, RoutingTier
from assistant.settings import AISettings
from config import LLM_FAST_TIMEOUT_SECONDS, LLM_STANDARD_TIMEOUT_SECONDS


def _model_for_provider(settings: AISettings, provider_name: str) -> str:
    return {
        "openrouter": settings.openrouter_model,
        "nvidia_nim": settings.nvidia_nim_model,
    }[provider_name]


def _route_target(
    settings: AISettings,
    provider_name: str,
    model: str,
    primary: ModelTarget,
) -> ModelTarget:
    provider = provider_name.strip().casefold()
    clean_model = model.strip()
    if provider == "primary":
        return ModelTarget(primary.provider_name, clean_model or primary.model)
    return ModelTarget(provider, clean_model or _model_for_provider(settings, provider))


def _positive_float_env(name: str, fallback: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return fallback
    try:
        value = float(raw)
    except ValueError:
        return fallback
    return value if value > 0 else fallback


def build_configured_llm_manager(settings: AISettings) -> LLMManager:
    """Build routes exactly as persisted/UI settings request.

    NVIDIA is not silently rewritten to OpenRouter. FAST/STANDARD retain their
    short deadlines for lightweight providers, but explicitly selected NVIDIA
    routes use the normal request timeout because the user knowingly selected a
    slower inference provider.

    When tiered routing is enabled, NVIDIA uses failover-first behavior: a timed
    out model is not retried repeatedly before the router can try another model.
    COMPLEX degrades through STANDARD and FAST before the configured fallback.
    """
    primary = ModelTarget(
        settings.provider_name,
        _model_for_provider(settings, settings.provider_name),
    )

    if settings.routing_enabled:
        fast = _route_target(
            settings, settings.fast_provider, settings.fast_model, primary
        )
        standard = _route_target(
            settings, settings.standard_provider, settings.standard_model, primary
        )
        complex_target = _route_target(
            settings, settings.complex_provider, settings.complex_model, primary
        )
        fallback = _route_target(
            settings, settings.fallback_provider, settings.fallback_model, primary
        )
    else:
        fast = standard = complex_target = fallback = primary

    targets = (primary, fast, standard, complex_target, fallback)
    providers: dict[str, LLMProvider] = {}
    for provider_name in dict.fromkeys(target.provider_name for target in targets):
        # NVIDIA timeouts are expensive. With routing enabled, the model chain is
        # the retry strategy, so do not spend multiple full timeouts on the exact
        # same model before trying a fallback candidate.
        effective_retry_count = (
            0
            if settings.routing_enabled and provider_name == "nvidia_nim"
            else settings.retry_count
        )
        try:
            providers[provider_name] = create_provider(
                name=provider_name,
                nvidia_base_url=settings.nvidia_nim_base_url,
                request_timeout_seconds=settings.request_timeout_seconds,
                max_tokens=settings.max_tokens,
                retry_count=effective_retry_count,
                retry_delay_seconds=settings.retry_delay_seconds,
            )
            if effective_retry_count != settings.retry_count:
                print(
                    f"[SENA ROUTER] provider={provider_name} retry_strategy=failover_first "
                    f"same_model_retries={effective_retry_count}"
                )
        except LLMConfigurationError as error:
            if provider_name == primary.provider_name:
                raise
            print(
                f"[SENA ROUTER] optional provider unavailable "
                f"provider={provider_name} detail={error}"
            )

    primary_provider = providers[primary.provider_name]
    tier_timeouts: dict[RoutingTier, float] = {}
    if settings.routing_enabled:
        tier_timeouts[RoutingTier.FAST] = (
            settings.request_timeout_seconds
            if fast.provider_name == "nvidia_nim"
            else min(
                settings.request_timeout_seconds,
                _positive_float_env(
                    "LLM_FAST_TIMEOUT_SECONDS", LLM_FAST_TIMEOUT_SECONDS
                ),
            )
        )
        tier_timeouts[RoutingTier.STANDARD] = (
            settings.request_timeout_seconds
            if standard.provider_name == "nvidia_nim"
            else min(
                settings.request_timeout_seconds,
                _positive_float_env(
                    "LLM_STANDARD_TIMEOUT_SECONDS", LLM_STANDARD_TIMEOUT_SECONDS
                ),
            )
        )

    return LLMManager(
        provider=primary_provider,
        provider_name=primary.provider_name,
        model=primary.model,
        providers=providers,
        routes={
            RoutingTier.FAST: fast,
            RoutingTier.STANDARD: standard,
            RoutingTier.COMPLEX: complex_target,
        },
        fallback_targets=(fallback, primary),
        tier_fallback_targets={
            RoutingTier.FAST: (fallback, primary),
            RoutingTier.STANDARD: (fast, fallback, primary),
            RoutingTier.COMPLEX: (standard, fast, fallback, primary),
        },
        tier_timeout_seconds=tier_timeouts,
        json_prefill_enabled=settings.json_prefill_enabled,
        prompt_cache_enabled=settings.prompt_cache_enabled,
    )


def build_runtime_assistant(manager_module: ModuleType) -> Any:
    """Use the explicit-route builder only for the production runtime build."""
    original_builder = manager_module.build_llm_manager
    manager_module.build_llm_manager = build_configured_llm_manager
    try:
        return manager_module.build_assistant_manager()
    finally:
        manager_module.build_llm_manager = original_builder


def install_routing_runtime_policy(manager_module: ModuleType) -> None:
    """Make hot-applied AI settings use the same explicit-route builder."""
    if getattr(manager_module, "_sena_explicit_route_policy_installed", False):
        return

    async def apply_settings(self: Any, settings: AISettings) -> None:
        replacement_llm = build_configured_llm_manager(settings)
        replacement_sessions = manager_module.SessionManager(
            timeout_seconds=settings.chat_timeout_seconds,
            history_max_messages=settings.history_max_messages,
        )
        async with self._exclusive_llm_access():
            previous_llm = self._llm
            previous_sessions = self.sessions
            self._llm = replacement_llm
            self.sessions = replacement_sessions
            self.settings = settings
            previous_sessions.clear()
            await previous_llm.close()

    manager_module.AssistantManager.apply_settings = apply_settings
    manager_module._sena_explicit_route_policy_installed = True
