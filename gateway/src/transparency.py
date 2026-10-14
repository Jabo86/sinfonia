"""
Sinfonia — Transparency

Calcola costi stimati ed effettivi, espone quote e statistiche.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

log = structlog.get_logger()


@dataclass
class CostEstimate:
    provider_id: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_usd: float
    is_paid: bool

    @property
    def is_free(self) -> bool:
        return not self.is_paid or self.estimated_usd == 0.0


@dataclass
class UsageSummary:
    provider_id: str
    requests_today: int
    tokens_today: int
    tokens_this_month: int
    estimated_cost_today_usd: float
    estimated_cost_month_usd: float
    budget_month_usd: float | None = None
    budget_remaining_usd: float | None = None
    budget_percent_used: float | None = None


class CostCalculator:
    """Calcola costi stimati in base a budget.yaml."""

    def __init__(self, config):
        self.config = config

    def estimate(
        self,
        provider_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> CostEstimate:
        """Stima il costo di una chiamata in base ai token."""
        is_paid = provider_id in self.config.paid_providers

        if not is_paid:
            return CostEstimate(
                provider_id=provider_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_usd=0.0,
                is_paid=False,
            )

        # Cerca i costi nel budget
        budget_provider = self.config.budget.per_provider.get(provider_id)
        if not budget_provider:
            return CostEstimate(provider_id, model, input_tokens, output_tokens, 0.0, True)

        model_costs = budget_provider.models.get(model, {})
        if not model_costs:
            # Prova con il primo modello della lista
            if budget_provider.models:
                model_costs = next(iter(budget_provider.models.values()))
            else:
                return CostEstimate(provider_id, model, input_tokens, output_tokens, 0.0, True)

        cost_in = model_costs.get("cost_per_1k_input_tokens", 0.0) * (input_tokens / 1000)
        cost_out = model_costs.get("cost_per_1k_output_tokens", 0.0) * (output_tokens / 1000)
        total = cost_in + cost_out

        return CostEstimate(
            provider_id=provider_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_usd=round(total, 6),
            is_paid=True,
        )

    def estimate_from_text(
        self,
        provider_id: str,
        model: str,
        input_text: str,
        expected_output_tokens: int = 500,
    ) -> CostEstimate:
        """Stima approssimativa basata sulla lunghezza del testo (4 char = 1 token)."""
        input_tokens = max(1, len(input_text) // 4)
        return self.estimate(provider_id, model, input_tokens, expected_output_tokens)


class UsageTracker:
    """Calcola statistiche d'uso per provider dal DB delle richieste."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    async def get_usage(self, provider_id: str, user_id: str = "local") -> UsageSummary:
        now = time.time()
        day_ago = now - 86400
        month_ago = now - 30 * 86400

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*), COALESCE(SUM(tokens), 0) FROM requests WHERE provider_id=? AND user_id=? AND timestamp>=?",
                (provider_id, user_id, day_ago),
            ) as cur:
                row = await cur.fetchone()
                reqs_today, tokens_today = row[0], row[1]

            async with db.execute(
                "SELECT COALESCE(SUM(tokens), 0) FROM requests WHERE provider_id=? AND user_id=? AND timestamp>=?",
                (provider_id, user_id, month_ago),
            ) as cur:
                row = await cur.fetchone()
                tokens_month = row[0]

        # Cerca il budget
        budget_month = None
        if hasattr(self, "_config") and self._config:
            bp = self._config.budget.per_provider.get(provider_id)
            if bp:
                budget_month = bp.monthly_budget_usd

        return UsageSummary(
            provider_id=provider_id,
            requests_today=reqs_today,
            tokens_today=tokens_today,
            tokens_this_month=tokens_month,
            estimated_cost_today_usd=0.0,
            estimated_cost_month_usd=0.0,
            budget_month_usd=budget_month,
            budget_remaining_usd=budget_month,
            budget_percent_used=0.0,
        )

    async def get_all_usage(self, provider_ids: list[str]) -> dict[str, UsageSummary]:
        return {pid: await self.get_usage(pid) for pid in provider_ids}


# --- Formattazione per CLI ------------------------------------------------

def format_number(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def format_usd(amount: float) -> str:
    if amount == 0:
        return "$0.00"
    if amount < 0.01:
        return f"${amount:.6f}"
    return f"${amount:.4f}"


def render_status_table(rows: list[dict]) -> str:
    """Renderizza una tabella ASCII per il comando status."""
    if not rows:
        return "Nessun provider configurato."

    headers = ["Provider", "RPM", "RPD", "Stato", "Cooldown"]
    widths = [20, 12, 14, 12, 12]

    def pad(s: str, w: int) -> str:
        return s + " " * (w - len(s)) if len(s) < w else s[:w]

    lines = []
    lines.append("  ".join(pad(h, w) for h, w in zip(headers, widths)))
    lines.append("─" * (sum(widths) + 2 * (len(widths) - 1)))

    for r in rows:
        rpm = f"{r['rpm_used']}/{r['rpm_limit']}" if r['rpm_limit'] else f"{r['rpm_used']}/∞"
        rpd = f"{r['rpd_used']}/{r['rpd_limit']}" if r['rpd_limit'] else f"{r['rpd_used']}/∞"
        stato = "🔴 cooldown" if r["in_cooldown"] else ("🟢 ok" if r["available"] else "🟡 esaurito")
        cooldown = f"{r['cooldown_remaining']}s" if r["in_cooldown"] else "—"
        lines.append("  ".join(pad(str(v), w) for v, w in zip(
            [r["name"], rpm, rpd, stato, cooldown], widths
        )))

    return "\n".join(lines)
