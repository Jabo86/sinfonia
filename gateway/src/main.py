"""
Sinfonia — Gateway Server

Espone un endpoint compatibile con l'API OpenAI (/v1/chat/completions).
Instrada ogni richiesta verso il provider free con piu quota residua.
Fallback automatico su 429, nel rispetto dei limiti dichiarati.

Uso:
    cd ~/sinfonia
    source venv/bin/activate
    uvicorn gateway.src.main:app --host 127.0.0.1 --port 8080 --reload

Test:
    curl http://127.0.0.1:8080/v1/models
    curl http://127.0.0.1:8080/health
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Aggiungi gateway/src al path per gli import interni
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import SinfoniaConfig, load_config  # noqa: E402
from quota_manager import QuotaManager  # noqa: E402
from router import NoProviderAvailable, Router  # noqa: E402

log = structlog.get_logger()


# --- Stato globale dell'app ------------------------------------------------

class AppState:
    config: SinfoniaConfig
    quota_manager: QuotaManager
    router: Router


state = AppState()


# --- Lifespan (startup/shutdown) -------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inizializza la configurazione e il router all'avvio del server."""
    log.info("sinfonia.startup")

    # Trova la root del progetto (due livelli sopra gateway/src)
    project_root = Path(__file__).resolve().parent.parent.parent
    providers_path = project_root / "config" / "providers.yaml"
    budget_path = project_root / "config" / "budget.yaml"
    env_path = project_root / ".env"

    # Carica config
    try:
        state.config = load_config(
            providers_path=providers_path,
            budget_path=budget_path,
            env_path=env_path,
        )
    except Exception as e:
        log.error("sinfonia.config_error", error=str(e))
        raise

    # Inizializza quota manager
    db_path = os.environ.get(
        "SINFONIA_DB_PATH",
        str(project_root / "data" / "sinfonia.db"),
    )
    state.quota_manager = QuotaManager(db_path)

    # Inizializza router
    state.router = Router(state.config, state.quota_manager)

    # Conta provider disponibili
    free_count = len(state.config.free_providers)
    paid_count = len(state.config.paid_providers)
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
        free_providers=free_count,
        paid_providers=paid_count,
        configured_free=configured_free,
        configured_paid=configured_paid,
        db_path=db_path,
    )

    if configured_free == 0:
        log.warning(
            "sinfonia.no_providers_configured",
            hint="Aggiungi almeno una chiave API in .env (es. GROQ_API_KEY)",
        )

    yield

    log.info("sinfonia.shutdown")


# --- App FastAPI -----------------------------------------------------------

app = FastAPI(
    title="Sinfonia Gateway",
    description="Ethical AI orchestration — Free-First, Paid-Ready",
    version="0.1.0",
    lifespan=lifespan,
)


# --- Modelli Pydantic (formato OpenAI) -------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    temperature: float | None = 0.7
    max_tokens: int | None = None
    stream: bool = False
    # Campi extra accettati e ignorati
    model_config = {"extra": "allow"}


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage


# --- Endpoints -------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check. Non consuma quota."""
    return {
        "status": "ok",
        "free_providers": len(state.config.free_providers),
        "paid_providers": len(state.config.paid_providers),
    }


@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    """
    Elenca i modelli disponibili (formato OpenAI).
    Mostra solo i provider con chiave API configurata.
    """
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

    # Modello "auto": sceglie automaticamente il provider migliore
    models.insert(0, {
        "id": "sinfonia/auto",
        "object": "model",
        "created": 0,
        "owned_by": "sinfonia",
    })

    return {"object": "list", "data": models}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> JSONResponse:
    """
    Endpoint principale. Instrada la richiesta verso il provider migliore.
    """
    messages = [m.model_dump() for m in request.messages]

    # Se il modello e "sinfonia/auto" o None, usa il router
    # Se e specificato come "sinfonia/<provider>/<model>", usa quel provider
    forced_provider: str | None = None
    forced_model: str | None = None

    if request.model and request.model.startswith("sinfonia/"):
        parts = request.model.split("/", 2)
        if len(parts) == 3 and parts[1] != "auto":
            forced_provider = parts[1]
            forced_model = parts[2]

    # Costruisci kwargs per il provider
    call_kwargs: dict[str, Any] = {}
    if request.temperature is not None:
        call_kwargs["temperature"] = request.temperature
    if request.max_tokens is not None:
        call_kwargs["max_tokens"] = request.max_tokens

    # Tenta con fallback chain
    decisions = await state.router.select_with_fallback(
        task_type="chat",
        max_attempts=3,
    )

    if not decisions:
        raise HTTPException(
            status_code=503,
            detail=(
                "Nessun provider disponibile. "
                "Verifica le chiavi API in .env o attendi il reset delle quote."
            ),
        )

    # Se l'utente ha forzato un provider, mettilo in testa
    if forced_provider:
        forced = [d for d in decisions if d.provider_id == forced_provider]
        if not forced:
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{forced_provider}' non disponibile.",
            )
        if forced_model:
            forced[0].model = forced_model
        decisions = forced + [d for d in decisions if d.provider_id != forced_provider]

    last_error: Exception | None = None
    for decision in decisions:
        try:
            log.info(
                "sinfonia.attempt",
                provider=decision.provider_id,
                model=decision.model,
            )
            data = await state.router.call_provider(
                decision,
                messages,
                **call_kwargs,
            )
            # Aggiungi prefisso per chiarezza
            data["model"] = f"sinfonia/{decision.provider_id}/{data.get('model', decision.model)}"
            return JSONResponse(content=data)

        except RuntimeError as e:
            last_error = e
            log.warning(
                "sinfonia.attempt_failed",
                provider=decision.provider_id,
                error=str(e)[:200],
            )
            continue

    raise HTTPException(
        status_code=502,
        detail=f"Tutti i provider hanno fallito. Ultimo errore: {last_error}",
    )


# --- Entry point per esecuzione diretta ------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8080,
        reload=False,
        log_level="info",
    )
