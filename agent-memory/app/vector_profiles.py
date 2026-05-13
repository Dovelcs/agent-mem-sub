from __future__ import annotations

from typing import Any


def default_profile(config: dict[str, Any]) -> str:
    profiles_cfg = dict(config.get("vector_profiles") or {})
    return str(profiles_cfg.get("default") or "default")


def profiles(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles_cfg = dict(config.get("vector_profiles") or {})
    raw = profiles_cfg.get("profiles") or {}
    if isinstance(raw, dict):
        return {str(name): dict(value or {}) for name, value in raw.items()}
    return {}


def profile_names(config: dict[str, Any]) -> list[str]:
    names = list(profiles(config).keys())
    if names:
        return names
    return [default_profile(config)]


def profile_config(config: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    selected = str(name or default_profile(config))
    return profiles(config).get(selected, {})


def qdrant_config(config: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    result = dict(config.get("qdrant") or {})
    result.update(dict(profile_config(config, name).get("qdrant") or {}))
    return result


def embedding_config(config: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    result = dict(config.get("embedding") or {})
    result.update(dict(profile_config(config, name).get("embedding") or {}))
    return result


def vector_cache_targets(config: dict[str, Any]) -> list[str]:
    cache_cfg = dict(config.get("vector_cache") or {})
    targets = cache_cfg.get("targets")
    if isinstance(targets, list) and targets:
        return [str(target) for target in targets]
    if profiles(config):
        return profile_names(config)
    return [default_profile(config)]


def vector_cache_config(config: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    cache_cfg = dict(config.get("vector_cache") or {})
    selected = str(name or default_profile(config))
    per_profile = cache_cfg.get("profiles") or {}
    result = {key: value for key, value in cache_cfg.items() if key not in {"profiles", "targets"}}
    if isinstance(per_profile, dict):
        result.update(dict(per_profile.get(selected) or {}))
    return result
