"""
Sinfonia — Model Updater

Scansiona periodicamente /v1/models dei provider e aggiorna providers.yaml.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import structlog
import yaml

log = structlog.get_logger()


async def discover_provider_models(
    provider_id: str,
    api_base: str,
    api_key: str | None = None,
) -> list[str]:
    url = f"{api_base.rstrip('/')}/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data:
                    models = [m["id"] for m in data["data"]]
                    log.info("model_updater.discovered", provider=provider_id, count=len(models))
                    return models
            else:
                log.warning("model_updater.http_error", provider=provider_id, status=resp.status_code)
    except Exception as e:
        log.warning("model_updater.discovery_failed", provider=provider_id, error=str(e))

    return []


async def update_providers_file(config_path: Path, new_models: dict[str, list[str]]) -> None:
    if not config_path.exists():
        log.error("model_updater.config_not_found", path=str(config_path))
        return

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    updated = False
    for provider_id, models in new_models.items():
        if provider_id in config.get("providers", {}):
            provider = config["providers"][provider_id]
            current = set(provider.get("models", []))
            discovered = set(models)
            added = discovered - current
            if added:
                provider["models"].extend(sorted(added))
                updated = True
                log.info("model_updater.models_added", provider=provider_id, models=list(added))

    if updated:
        with config_path.open("w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        log.info("model_updater.config_updated", path=str(config_path))
    else:
        log.info("model_updater.no_changes")


async def run_update_cycle(config_path: Path, config_loader) -> None:
    log.info("model_updater.cycle_start")
    cfg = config_loader.load_config()

    new_models: dict[str, list[str]] = {}
    for pid, provider in cfg.free_providers.items():
        api_key = cfg.get_api_key(pid)
        if api_key:
            models = await discover_provider_models(pid, provider.api_base, api_key)
            if models:
                new_models[pid] = models

    await update_providers_file(config_path, new_models)
    log.info("model_updater.cycle_end")


async def scheduler_loop(config_path: Path, config_loader, interval_hours: int = 24) -> None:
    while True:
        try:
            await run_update_cycle(config_path, config_loader)
        except Exception as e:
            log.error("model_updater.scheduler_error", error=str(e))
        await asyncio.sleep(interval_hours * 3600)
