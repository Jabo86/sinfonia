"""
Sinfonia — Ensemble Mode

Fan-out verso N provider in parallelo, fan-in con giudice locale (Ollama).
Il giudice NON consuma quota API: gira sul computer dell'utente.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

log = structlog.get_logger()


@dataclass
class PanelResponse:
    provider_id: str
    model: str
    content: str
    tokens: int
    elapsed_ms: int
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return self.error is None and bool(self.content)


@dataclass
class EnsembleResult:
    final_content: str
    judge_model: str
    panel: list[PanelResponse] = field(default_factory=list)
    judge_elapsed_ms: int = 0
    total_elapsed_ms: int = 0

    @property
    def successful_panels(self) -> list[PanelResponse]:
        return [p for p in self.panel if p.is_success]

    @property
    def total_tokens(self) -> int:
        return sum(p.tokens for p in self.panel)

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_content": self.final_content,
            "judge_model": self.judge_model,
            "panel": [
                {
                    "provider_id": p.provider_id,
                    "model": p.model,
                    "content": p.content[:200] + ("..." if len(p.content) > 200 else ""),
                    "tokens": p.tokens,
                    "elapsed_ms": p.elapsed_ms,
                    "error": p.error,
                }
                for p in self.panel
            ],
            "successful_panels": len(self.successful_panels),
            "total_panels": len(self.panel),
            "total_tokens": self.total_tokens,
            "judge_elapsed_ms": self.judge_elapsed_ms,
            "total_elapsed_ms": self.total_elapsed_ms,
        }


JUDGE_PROMPT_TEMPLATE = """Sei un giudice imparziale che sintetizza risposte di diverse AI.

L'utente ha chiesto:
---
{user_question}
---

Le seguenti AI hanno risposto:

{panel_responses}

Il tuo compito:
1. Identifica i punti di CONSENSO tra le risposte.
2. Identifica le CONTRADDIZIONI o i punti in cui divergono.
3. Scrivi una RISPOSTA FINALE SINTETIZZATA in italiano che sia piu completa
   e accurata di qualsiasi singola risposta.
4. Rispondi SOLO con la sintesi finale, senza preamboli o meta-commenti.
"""


class EnsembleOrchestrator:
    def __init__(self, router, judge_model: str = "llama3.2:3b", judge_url: str = "http://localhost:11434"):
        self.router = router
        self.judge_model = judge_model
        self.judge_url = judge_url.rstrip("/")

    async def _call_panel_member(self, decision, messages, **kwargs):
        start = time.time()
        try:
            data = await self.router.call_provider(decision, messages, **kwargs)
            content = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", 0)
            return PanelResponse(
                provider_id=decision.provider_id,
                model=decision.model,
                content=content,
                tokens=tokens,
                elapsed_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            log.warning("ensemble.panel_member_failed", provider=decision.provider_id, error=str(e)[:200])
            return PanelResponse(
                provider_id=decision.provider_id,
                model=decision.model,
                content="",
                tokens=0,
                elapsed_ms=int((time.time() - start) * 1000),
                error=str(e)[:300],
            )

    async def _call_judge(self, user_question: str, panel):
        responses_text = "\n\n".join(
            f"### {p.provider_id} ({p.model})\n{p.content}"
            for p in panel
            if p.is_success
        )
        if not responses_text:
            return "Nessuna risposta valida dal panel."

        prompt = JUDGE_PROMPT_TEMPLATE.format(
            user_question=user_question,
            panel_responses=responses_text,
        )
        payload = {
            "model": self.judge_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3},
        }
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(f"{self.judge_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()

    async def run(self, decisions, messages, judge_override=None, **kwargs):
        if not decisions:
            raise ValueError("Ensemble richiede almeno un provider nel panel")

        start_total = time.time()
        log.info("ensemble.fanout", panel_size=len(decisions))
        tasks = [self._call_panel_member(d, messages, **kwargs) for d in decisions]
        panel = await asyncio.gather(*tasks)

        successful = [p for p in panel if p.is_success]
        log.info("ensemble.panel_complete", successful=len(successful), total=len(panel))

        user_question = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_question = m.get("content", "")
                break

        judge_model = judge_override or self.judge_model
        judge_start = time.time()

        if len(successful) == 1:
            final_content = successful[0].content
            judge_model = f"passthrough/{successful[0].provider_id}"
        elif not successful:
            final_content = "Tutte le AI del panel hanno fallito. Riprova piu tardi."
            judge_model = "none"
        else:
            try:
                final_content = await self._call_judge(user_question, panel)
            except Exception as e:
                log.error("ensemble.judge_failed", error=str(e))
                longest = max(successful, key=lambda p: len(p.content))
                final_content = longest.content
                judge_model = f"fallback/{longest.provider_id}"

        judge_elapsed = int((time.time() - judge_start) * 1000)
        total_elapsed = int((time.time() - start_total) * 1000)

        log.info("ensemble.complete", judge=judge_model, judge_ms=judge_elapsed, total_ms=total_elapsed)

        return EnsembleResult(
            final_content=final_content,
            judge_model=judge_model,
            panel=list(panel),
            judge_elapsed_ms=judge_elapsed,
            total_elapsed_ms=total_elapsed,
        )
