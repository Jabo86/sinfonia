"""
Sinfonia — Router

Sceglie quale provider usare per ogni richiesta in base a:
1. Disponibilita (non in cooldown, con capacita residua)
2. Strategia quota_aware (piu quota residua = priorita)
3. Preferenze utente (free_first, paid_first, budget_aware)

Il Router NON aggira MAI i limiti. Se tutti i provider sono esauriti,
restituisce un errore chiaro all'utente.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from config_loader import Provider, SinfoniaConfig
from quota_manager import QuotaManager, QuotaStatus

log = structlog.get_logger()


# --- Modelli ---------------------------------------------------------------

@dataclass
class RouteDecision:
    """Decisione di routing."""
    provider_id: str
    provider: Provider
    model: str
    quota_status: QuotaStatus
    is_paid: bool
    reason: str


class NoProviderAvailable(Exception):
    """Nessun provider disponibile (quote esaurite o tutti in cooldown)."""
    pass


# --- Router ----------------------------------------------------------------

class Router:
    """
    Router quota-aware con fallback.

    Uso tipico:
        router = Router(config, quota_manager)
        decision = await router.select_provider(task_type="chat")
        # ... usa decision.provider ...
        await router.report_result(decision.provider_id, success=True, tokens=150)
    """

    def __init__(self, config: SinfoniaConfig, quota_manager: QuotaManager):
        self.config = config
        self.qm = quota_manager

    # --- Selezione ---------------------------------------------------------

    async def select_provider(
        self,
        task_type: str = "chat",
        exclude_providers: list[str] | None = None,
        allow_paid: bool | None = None,
    ) -> RouteDecision:
        """
        Seleziona il provider migliore per la richiesta.

        Args:
            task_type: tipo di task (chat, code, long_context, ...). Per ora non usato.
            exclude_providers: provider da escludere (es. quelli gia provati e falliti)
            allow_paid: se True, considera anche i provider paid. Se None, usa config.

        Returns:
            RouteDecision con il provider scelto.

        Raises:
            NoProviderAvailable: se nessun provider ha capacita residua.
        """
        exclude = set(exclude_providers or [])

        if allow_paid is None:
            mode = self.config.providers.routing.paid_routing.mode
            allow_paid = mode in ("paid_first", "budget_aware")

        # 1. Raccogli tutti i provider candidati con le loro chiavi API configurate
        candidates = await self._collect_candidates(
            exclude=exclude, allow_paid=allow_paid
        )

        if not candidates:
            raise NoProviderAvailable(
                "Nessun provider disponibile. "
                "Verifica le tue chiavi API in .env o attendi il reset delle quote."
            )

        # 2. Ordina per capacita residua
        candidates.sort(key=lambda d: d.quota_status.free_capacity_score, reverse=True)

        # 3. Scegli il primo
        decision = candidates[0]
        log.info(
            "router.selected",
            provider=decision.provider_id,
            model=decision.model,
            is_paid=decision.is_paid,
            reason=decision.reason,
            quota_score=decision.quota_status.free_capacity_score,
        )
        return decision

    async def _collect_candidates(
        self, exclude: set[str], allow_paid: bool
    ) -> list[RouteDecision]:
        """Raccoglie tutti i provider con chiave API configurata e capacita residua."""
        candidates: list[RouteDecision] = []

        # Provider free
        for pid, provider in self.config.free_providers.items():
            if pid in exclude:
                continue
            if not self.config.get_api_key(pid):
                continue

            limits = provider.free_tier.limits if provider.free_tier else {}
            status = await self.qm.get_status(
                pid,
                rpm_limit=limits.get("rpm"),
                rpd_limit=limits.get("rpd"),
                tpd_limit=limits.get("tokens_per_day"),
            )
            if not status.is_available:
                log.debug(
                    "router.skip_provider",
                    provider=pid,
                    reason="cooldown" if status.is_in_cooldown else "no_capacity",
                )
                continue

            candidates.append(RouteDecision(
                provider_id=pid,
                provider=provider,
                model=provider.models[0] if provider.models else "unknown",
                quota_status=status,
                is_paid=False,
                reason="free_tier_available",
            ))

        # Provider paid (solo se allow_paid)
        if allow_paid:
            for pid, provider in self.config.paid_providers.items():
                if pid in exclude:
                    continue
                if not self.config.get_api_key(pid):
                    continue

                status = await self.qm.get_status(pid)  # no limiti hardcoded per paid
                if not status.is_available:
                    continue

                candidates.append(RouteDecision(
                    provider_id=pid,
                    provider=provider,
                    model=provider.models[0] if provider.models else "unknown",
                    quota_status=status,
                    is_paid=True,
                    reason="paid_provider_available",
                ))

        return candidates

    # --- Fallback chain ----------------------------------------------------

    async def select_with_fallback(
        self,
        task_type: str = "chat",
        max_attempts: int = 3,
        allow_paid: bool | None = None,
    ) -> list[RouteDecision]:
        """
        Restituisce una lista ordinata di provider da tentare in sequenza.

        Il chiamante prova il primo; se fallisce con 429, passa al secondo, ecc.
        """
        excluded: list[str] = []
        decisions: list[RouteDecision] = []

        for _ in range(max_attempts):
            try:
                d = await self.select_provider(
                    task_type=task_type,
                    exclude_providers=excluded,
                    allow_paid=allow_paid,
                )
                decisions.append(d)
                excluded.append(d.provider_id)
            except NoProviderAvailable:
                break

        return decisions

    # --- Reporting ---------------------------------------------------------

    async def report_result(
        self,
        provider_id: str,
        success: bool,
        tokens: int = 0,
        status_code: int | None = None,
    ) -> None:
        """Registra il risultato di una chiamata per aggiornare le quote."""
        was_429 = status_code == 429
        await self.qm.record_request(
            provider_id,
            tokens=tokens,
            status_code=status_code,
            was_429=was_429,
        )

        if not success and not was_429:
            log.warning(
                "router.request_failed",
                provider=provider_id,
                status_code=status_code,
            )

    # --- HTTP call ---------------------------------------------------------

    async def call_provider(
        self,
        decision: RouteDecision,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Esegue la chiamata HTTP al provider scelto.

        Returns:
            Risposta JSON del provider (formato OpenAI chat completions).
        """
        api_key = self.config.get_api_key(decision.provider_id)
        if not api_key:
            raise ValueError(f"API key mancante per {decision.provider_id}")

        url = f"{decision.provider.api_base.rstrip('/')}/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Header speciali per OpenRouter
        if decision.provider_id == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/Jabo86/sinfonia"
            headers["X-Title"] = "Sinfonia"

        payload = {
            "model": decision.model,
            "messages": messages,
            **kwargs,
        }

        start = time.time()
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as e:
                await self.report_result(decision.provider_id, success=False)
                raise RuntimeError(f"Errore HTTP verso {decision.provider_id}: {e}") from e

        elapsed_ms = int((time.time() - start) * 1000)

        if resp.status_code == 429:
            await self.report_result(
                decision.provider_id, success=False, status_code=429
            )
            raise RuntimeError(
                f"Provider {decision.provider_id} ha risposto 429 (rate limit)"
            )

        if resp.status_code >= 400:
            await self.report_result(
                decision.provider_id, success=False, status_code=resp.status_code
            )
            raise RuntimeError(
                f"Provider {decision.provider_id} errore {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()

        # Estrai token usati (formato OpenAI)
        usage = data.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)
        await self.report_result(
            decision.provider_id,
            success=True,
            tokens=total_tokens,
            status_code=200,
        )

        log.info(
            "router.call_success",
            provider=decision.provider_id,
            model=decision.model,
            elapsed_ms=elapsed_ms,
            tokens=total_tokens,
        )

        return data


# --- Test rapido -----------------------------------------------------------

async def _test() -> None:
    """Test del router senza chiamate HTTP reali."""
    import tempfile
    from pathlib import Path

    cfg = None
    try:
        from config_loader import load_config
        cfg = load_config()
    except FileNotFoundError as e:
        print(f"Config non trovata: {e}")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        qm = QuotaManager(Path(tmpdir) / "test.db")
        router = Router(cfg, qm)

        # Simula un ambiente senza chiavi API per verificare il comportamento
        print("Test router: senza chiavi API configurate")
        try:
            await router.select_provider()
            print("  ERRORE: dovrebbe aver sollevato NoProviderAvailable")
        except NoProviderAvailable as e:
            print(f"  OK: NoProviderAvailable sollevato correttamente")
            print(f"  Messaggio: {e}")

        print("\nTest router: comportamento con chiave finta")
        import os
        os.environ["GROQ_API_KEY"] = "fake_key_for_test"
        try:
            decision = await router.select_provider()
            print(f"  Provider scelto: {decision.provider_id}")
            print(f"  Modello: {decision.model}")
            print(f"  Reason: {decision.reason}")
            print(f"  Quota score: {decision.quota_status.free_capacity_score}")
        except NoProviderAvailable as e:
            print(f"  ERRORE: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(_test())
