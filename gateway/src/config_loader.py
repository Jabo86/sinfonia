"""
Sinfonia — Config Loader

Legge providers.yaml e budget.yaml e li espone come oggetti tipizzati.
Nessuna logica di routing qui: solo parsing e validazione.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


# --- Modelli Pydantic ------------------------------------------------------

class FreeTier(BaseModel):
    available: bool = True
    credit_card_required: bool = False
    limits: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class Provider(BaseModel):
    name: str
    api_base: str
    api_key_env: str
    openai_compatible: bool = True
    adapter: str | None = None
    free_tier: FreeTier | None = None
    billing: dict[str, Any] | None = None
    models: list[str] = Field(default_factory=list)


class RoutingPaidConfig(BaseModel):
    mode: str = "free_first"
    confirm_before_paid: bool = True
    show_cost_estimate: bool = True


class RoutingConfig(BaseModel):
    default_mode: str = "single"
    strategy: str = "quota_aware"
    fallback_on_429: bool = True
    paid_routing: RoutingPaidConfig = Field(default_factory=RoutingPaidConfig)


class EnsembleConfig(BaseModel):
    enabled: bool = False
    panel_size: int = 3
    judge: str = "ollama/qwen3"
    min_provider_families: int = 2
    warn_before_execution: bool = True


class LocalConfig(BaseModel):
    enabled: bool = True
    provider: str = "ollama"
    api_base: str = "http://localhost:11434"
    models: dict[str, str] = Field(default_factory=dict)


class ProvidersFile(BaseModel):
    version: int
    providers: dict[str, Provider]
    paid_providers: dict[str, Provider] = Field(default_factory=dict)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    ensemble: EnsembleConfig = Field(default_factory=EnsembleConfig)
    local: LocalConfig = Field(default_factory=LocalConfig)


class GlobalBudget(BaseModel):
    monthly_budget_usd: float = 20.0
    hard_limit: bool = True
    warning_threshold: float = 0.80
    currency: str = "USD"


class ProviderBudget(BaseModel):
    monthly_budget_usd: float
    hard_limit: bool = True
    warn_at_percent: int = 80
    models: dict[str, dict[str, float]] = Field(default_factory=dict)


class BudgetFile(BaseModel):
    version: int
    global_budget: GlobalBudget = Field(alias="global")
    per_provider: dict[str, ProviderBudget] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


# --- Caricamento -----------------------------------------------------------

class SinfoniaConfig:
    """Configurazione completa di Sinfonia."""

    def __init__(self, providers: ProvidersFile, budget: BudgetFile):
        self.providers = providers
        self.budget = budget

    @property
    def free_providers(self) -> dict[str, Provider]:
        return {
            k: v for k, v in self.providers.providers.items()
            if v.free_tier and v.free_tier.available
        }

    @property
    def paid_providers(self) -> dict[str, Provider]:
        return self.providers.paid_providers

    def get_api_key(self, provider_id: str) -> str | None:
        """Legge la chiave API del provider dalle variabili d'ambiente."""
        provider = self.providers.providers.get(provider_id) \
            or self.providers.paid_providers.get(provider_id)
        if not provider:
            return None
        return os.environ.get(provider.api_key_env)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"File di configurazione non trovato: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(
    providers_path: str | Path = "config/providers.yaml",
    budget_path: str | Path = "config/budget.yaml",
    env_path: str | Path = ".env",
) -> SinfoniaConfig:
    """
    Carica la configurazione completa di Sinfonia.
    """
    env_file = Path(env_path)
    if env_file.exists():
        load_dotenv(env_file)

    providers_data = _load_yaml(Path(providers_path))
    budget_data = _load_yaml(Path(budget_path))

    providers = ProvidersFile(**providers_data)
    budget = BudgetFile(**budget_data)

    return SinfoniaConfig(providers=providers, budget=budget)


# --- Test rapido -----------------------------------------------------------

if __name__ == "__main__":
    cfg = load_config()
    print(f"Provider free caricati: {len(cfg.free_providers)}")
    for pid in cfg.free_providers:
        print(f"  - {pid}: {cfg.free_providers[pid].name}")
    print(f"Provider paid caricati: {len(cfg.paid_providers)}")
    for pid in cfg.paid_providers:
        print(f"  - {pid}: {cfg.paid_providers[pid].name}")
    print(f"Budget globale: ${cfg.budget.global_budget.monthly_budget_usd}")
    print(f"Modalita default: {cfg.providers.routing.default_mode}")
