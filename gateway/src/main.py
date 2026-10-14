"""
Sinfonia — Gateway Server

Espone un endpoint compatibile con l'API OpenAI (/v1/chat/completions).
Instrada ogni richiesta verso il provider free con piu quota residua.
Supporta continuita conversazione, auto-guarigione e auto-scoperta modelli.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

import config_loader
from config_loader import SinfoniaConfig, load_config
from conversation_state import ConversationStore
from model_updater import scheduler_loop
from quota_manager import QuotaManager
from router import NoProviderAvailable, Router
from self_healer import SelfHealer
from transparency import CostCalculator, UsageTracker

log = structlog.get_logger()


class AppState:
    config: SinfoniaConfig
    quota_manager: QuotaManager
    router: Router
    conversation_store: ConversationStore
    self_healer: SelfHealer
    cost_calculator: CostCalculator
    usage_tracker: UsageTracker


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("sinfonia.startup")

    project_root = Path(__file__).resolve().parent.parent.parent
    providers_path = project_root / "config" / "providers.yaml"
    budget_path = project_root / "config" / "budget.yaml"
    env_path = project_root / ".env"

    try:
        state.config = load_config(
            providers_path=providers_path,
            budget_path=budget_path,
            env_path=env_path,
        )
    except Exception as e:
        log.error("sinfonia.config_error", error=str(e))
        raise

    db_path = os.environ.get(
        "SINFONIA_DB_PATH",
        str(project_root / "data" / "sinfonia.db"),
    )
    state.quota_manager = QuotaManager(db_path)
    state.conversation_store = ConversationStore(db_path)
    state.self_healer = SelfHealer()
    state.cost_calculator = CostCalculator(state.config)
    state.usage_tracker = UsageTracker(db_path)
    state.router = Router(state.config, state.quota_manager)

    configured_free = sum(
        1 for pid in state.config.free_providers
        if state.config.get_api_key(pid)
    )
    configured_paid = sum(
        1 for pid in state.config.paid_providers
        if state.config.get_api_key(pid)
    )

    log.info(
        "sinfonia.ready",
        free_providers=len(state.config.free_providers),
        paid_providers=len(state.config.paid_providers),
        configured_free=configured_free,
        configured_paid=configured_paid,
        db_path=db_path,
    )

    # Avvia lo scheduler di aggiornamento modelli
    asyncio.create_task(
        scheduler_loop(
            config_path=providers_path,
            config_loader=config_loader,
            interval_hours=24,
        )
    )

    yield
    log.info("sinfonia.shutdown")


app = FastAPI(
    title="Sinfonia Gateway",
    description="Ethical AI orchestration — Free-First, Paid-Ready",
    version="0.2.0",
    lifespan=lifespan,
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    temperature: float | None = 0.7
    max_tokens: int | None = None
    stream: bool = False
    conversation_id: str | None = None
    model_config = {"extra": "allow"}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "free_providers": len(state.config.free_providers),
        "paid_providers": len(state.config.paid_providers),
    }


@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    models = []
    for pid, provider in state.config.free_providers.items():
        if not state.config.get_api_key(pid):
            continue
        for model_name in provider.models:
            models.append({
                "id": f"sinfonia/{pid}/{model_name}",
                "object": "model",
                "created": 0,
                "owned_by": f"sinfonia-free/{pid}",
            })
    for pid, provider in state.config.paid_providers.items():
        if not state.config.get_api_key(pid):
            continue
        for model_name in provider.models:
            models.append({
                "id": f"sinfonia/{pid}/{model_name}",
                "object": "model",
                "created": 0,
                "owned_by": f"sinfonia-paid/{pid}",
            })
    models.insert(0, {
        "id": "sinfonia/auto",
        "object": "model",
        "created": 0,
        "owned_by": "sinfonia",
    })
    return {"object": "list", "data": models}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> JSONResponse:
    # --- Gestione conversazione persistente ---
    conv_id = request.conversation_id
    if conv_id:
        existing = await state.conversation_store.get_messages(conv_id)
        if existing:
            history = [{"role": m.role, "content": m.content} for m in existing]
        else:
            conv_id = await state.conversation_store.create_conversation()
            history = []
    else:
        conv_id = await state.conversation_store.create_conversation()
        history = []

    new_messages = [m.model_dump() for m in request.messages]
    messages = history + new_messages

    # Salva i nuovi messaggi utente
    for msg in request.messages:
        await state.conversation_store.add_message(conv_id, msg.role, msg.content)

    # --- Determina provider forzato se il modello e specificato ---
    forced_provider: str | None = None
    forced_model: str | None = None
    if request.model and request.model.startswith("sinfonia/"):
        parts = request.model.split("/", 2)
        if len(parts) == 3 and parts[1] != "auto":
            forced_provider = parts[1]
            forced_model = parts[2]

    call_kwargs: dict[str, Any] = {}
    if request.temperature is not None:
        call_kwargs["temperature"] = request.temperature
    if request.max_tokens is not None:
        call_kwargs["max_tokens"] = request.max_tokens

    # --- Seleziona provider con fallback ---
    decisions = await state.router.select_with_fallback(task_type="chat", max_attempts=3)
    if not decisions:
        raise HTTPException(status_code=503, detail="Nessun provider disponibile.")

    if forced_provider:
        forced = [d for d in decisions if d.provider_id == forced_provider]
        if not forced:
            # Tenta comunque il provider forzato
            all_decisions = await state.router.select_with_fallback(
                task_type="chat", max_attempts=10
            )
            forced = [d for d in all_decisions if d.provider_id == forced_provider]
            if not forced:
                raise HTTPException(status_code=400, detail=f"Provider '{forced_provider}' non disponibile.")
        if forced_model:
            forced[0].model = forced_model
        decisions = forced + [d for d in decisions if d.provider_id != forced_provider]

    last_error: Exception | None = None
    for decision in decisions:
        try:
            log.info("sinfonia.attempt", provider=decision.provider_id, model=decision.model)
            data = await state.router.call_provider(decision, messages, **call_kwargs)
            data["model"] = f"sinfonia/{decision.provider_id}/{data.get('model', decision.model)}"

            # Salva la risposta dell'assistente
            try:
                assistant_content = data["choices"][0]["message"]["content"]
                await state.conversation_store.add_message(conv_id, "assistant", assistant_content)
            except (KeyError, IndexError):
                pass

            data["conversation_id"] = conv_id
            return JSONResponse(content=data)

        except RuntimeError as e:
            last_error = e
            log.warning("sinfonia.attempt_failed", provider=decision.provider_id, error=str(e)[:200])
            continue

    raise HTTPException(status_code=502, detail=f"Tutti i provider hanno fallito. Ultimo errore: {last_error}")




@app.get("/v1/quota")
async def get_quota() -> dict[str, Any]:
    """Quote residue di tutti i provider free."""
    result = {}
    for pid, provider in state.config.free_providers.items():
        limits = provider.free_tier.limits if provider.free_tier else {}
        status = await state.quota_manager.get_status(
            pid,
            rpm_limit=limits.get("rpm"),
            rpd_limit=limits.get("rpd"),
            tpd_limit=limits.get("tokens_per_day"),
        )
        result[pid] = {
            "name": provider.name,
            "requests_this_minute": status.requests_this_minute,
            "requests_today": status.requests_today,
            "tokens_today": status.tokens_today,
            "rpm_limit": status.rpm_limit,
            "rpd_limit": status.rpd_limit,
            "tpd_limit": status.tpd_limit,
            "available": status.is_available,
            "in_cooldown": status.is_in_cooldown,
            "cooldown_remaining_seconds": status.cooldown_remaining,
        }
    return result


@app.get("/v1/usage")
async def get_usage() -> dict[str, Any]:
    """Statistiche d'uso per provider."""
    result = {}
    for pid, provider in state.config.free_providers.items():
        s = await state.usage_tracker.get_usage(pid)
        result[pid] = {
            "name": provider.name,
            "requests_today": s.requests_today,
            "tokens_today": s.tokens_today,
            "tokens_this_month": s.tokens_this_month,
        }
    for pid, provider in state.config.paid_providers.items():
        s = await state.usage_tracker.get_usage(pid)
        result[pid] = {
            "name": provider.name,
            "requests_today": s.requests_today,
            "tokens_today": s.tokens_today,
            "tokens_this_month": s.tokens_this_month,
            "budget_month_usd": s.budget_month_usd,
            "budget_remaining_usd": s.budget_remaining_usd,
        }
    return result


@app.post("/v1/estimate")
async def estimate_cost(request: ChatCompletionRequest) -> dict[str, Any]:
    """Stima il costo di una richiesta PRIMA di eseguirla."""
    total_text = " ".join(m.content for m in request.messages)
    expected_output = request.max_tokens or 500

    estimates = {}
    for pid, provider in state.config.paid_providers.items():
        if not state.config.get_api_key(pid):
            continue
        for model in provider.models:
            est = state.cost_calculator.estimate_from_text(
                pid, model, total_text, expected_output
            )
            estimates[f"{pid}/{model}"] = {
                "input_tokens_estimated": est.input_tokens,
                "output_tokens_estimated": est.output_tokens,
                "estimated_usd": est.estimated_usd,
            }

    free_info = {}
    for pid, provider in state.config.free_providers.items():
        if state.config.get_api_key(pid):
            free_info[pid] = {
                "name": provider.name,
                "cost": 0.0,
                "models": provider.models[:3],
            }

    return {
        "free_options": free_info,
        "paid_estimates": estimates,
        "note": "Usa free_options per costo zero. Le stime paid sono approssimative.",
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=False)
