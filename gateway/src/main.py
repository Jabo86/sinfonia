"""
Sinfonia — Gateway Server

Espone un endpoint compatibile con l'API OpenAI (/v1/chat/completions).
Instrada ogni richiesta verso il provider free con piu quota residua.
Supporta continuita conversazione, auto-guarigione e auto-scoperta modelli.
"""

from __future__ import annotations

from datetime import datetime

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

import config_loader
from config_loader import SinfoniaConfig, load_config
from conversation_state import ConversationStore
from model_updater import scheduler_loop
from quota_manager import QuotaManager
from router import NoProviderAvailable, Router
from ensemble import EnsembleOrchestrator
from voice_api import router as voice_router
from self_healer import SelfHealer
from image_providers import ImageRouter
from intent_classifier import Intent, classify, extract_prompt
from realtime import build_system_prompt, build_voice_prompt, detect_weather_city, get_weather, GIORNI, MESI
from profession_manager import get_profession_manager
from file_reader import read_file_bytes
from music_generator import MusicGenerator
from translator import Translator
from video_generator import VideoGenerator

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
    ensemble: EnsembleOrchestrator
    image_router: ImageRouter
    video_generator: VideoGenerator
    music_generator: MusicGenerator
    translator: Translator


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
    judge_model = state.config.providers.ensemble.judge.split("/")[-1]
    state.ensemble = EnsembleOrchestrator(state.router, judge_model=judge_model)
    state.image_router = ImageRouter()
    state.video_generator = VideoGenerator()
    state.music_generator = MusicGenerator()
    state.translator = Translator()

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

# Voice API
app.include_router(voice_router)


# Mount UI statica
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(_static_dir), html=True), name="ui")



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
    voice_mode: bool = False
    profession: str | None = None
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




def _detect_creative_intent(text: str) -> str | None:
    """Rileva se il messaggio chiede un contenuto creativo."""
    t = text.lower()
    # Canzone
    if any(k in t for k in ["canzone", "song", "testo di una canzone", "scrivimi una canzone", "creami una canzone", "componi una canzone", "lyrics"]):
        return "song"
    # Poesia
    if any(k in t for k in ["poesia", "poema", "versi", "poetami", "scrivi una poesia"]):
        return "poem"
    # Email
    if any(k in t for k in ["scrivi un'email", "scrivi una mail", "componi un'email", "redigi una mail"]):
        return "email"
    # Storia/racconto
    if any(k in t for k in ["racconto", "storia breve", "fiaba", "favola", "scrivi una storia"]):
        return "story"
    return None


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
    # Priorita: profession > voice_mode > default
    if request.profession:
        try:
            pm = get_profession_manager()
            base_prompt = pm.get_system_prompt(request.profession)
            if request.voice_mode:
                # In modalita voce, aggiungi istruzioni voce al prompt del profilo
                voice_suffix = "\n\nIMPORTANTE: rispondi in modo naturale per essere letto ad alta voce, senza markdown o simboli."
                SISTEMA_SINFONIA = base_prompt + voice_suffix
            else:
                SISTEMA_SINFONIA = base_prompt
            log.info("sinfonia.profession_active", profession=request.profession)
        except Exception as e:
            log.warning("sinfonia.profession_error", profession=request.profession, error=str(e))
            SISTEMA_SINFONIA = build_voice_prompt() if request.voice_mode else build_system_prompt()
    elif request.voice_mode:
        SISTEMA_SINFONIA = build_voice_prompt()
    else:
        SISTEMA_SINFONIA = build_system_prompt()
    # Costruisci con system prompt + rinforzo data inline (i modelli piccoli tendono a ignorare il solo system)
    _now = datetime.now()
    _data_str = f"{GIORNI[_now.weekday()]} {_now.day} {MESI[_now.month - 1]} {_now.year}"
    _ora_str = _now.strftime("%H:%M")
    _date_reinforcement = {
        "role": "system",
        "content": f"RICORDA: Oggi e' {_data_str}, ore {_ora_str}. Se ti viene chiesta la data, rispondi esattamente: 'Oggi e' {_data_str}.'"
    }
    messages = history + [
        {"role": "system", "content": SISTEMA_SINFONIA},
        _date_reinforcement,
    ] + new_messages

    # Contesto in tempo reale: meteo (solo se la domanda lo richiede)
    _last_user = ""
    for _m in reversed(new_messages):
        if _m.get("role") == "user":
            _last_user = _m.get("content", "")
            break
    _city = detect_weather_city(_last_user)
    if _city:
        try:
            _weather = await get_weather(_city)
            _wtext = (
                f"DATI METEO IN TEMPO REALE per {_weather['city']} "
                f"(fonte: wttr.in, rilevati adesso): "
                f"temperatura {_weather['temp_C']} C, "
                f"percepita {_weather['feels_like_C']} C, "
                f"condizioni: {_weather['description']}, "
                f"umidita {_weather['humidity']}%, "
                f"vento {_weather['wind_kmph']} km/h {_weather['wind_dir']}, "
                f"indice UV {_weather['uv_index']}. "
                f"Riporta questi dati nella tua risposta."
            )
            messages.append({"role": "system", "content": _wtext})
            log.info("realtime.weather_injected", city=_city)
        except Exception as _e:
            log.warning("realtime.weather_failed", city=_city, error=str(_e))

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




class EnsembleRequest(BaseModel):
    messages: list[ChatMessage]
    panel_size: int | None = None
    judge_model: str | None = None
    temperature: float | None = 0.7


@app.post("/v1/ensemble")
async def ensemble_chat(request: EnsembleRequest) -> JSONResponse:
    """Modalita Ensemble: N provider rispondono in parallelo, un giudice locale sintetizza."""
    messages = [m.model_dump() for m in request.messages]
    panel_size = request.panel_size or state.config.providers.ensemble.panel_size

    decisions = await state.router.select_with_fallback(task_type="chat", max_attempts=panel_size)
    if not decisions:
        raise HTTPException(status_code=503, detail="Nessun provider disponibile per il panel.")

    log.info("sinfonia.ensemble_start", panel=[d.provider_id for d in decisions], judge=request.judge_model or state.config.providers.ensemble.judge)

    call_kwargs = {}
    if request.temperature is not None:
        call_kwargs["temperature"] = request.temperature

    result = await state.ensemble.run(
        decisions=decisions,
        messages=messages,
        judge_override=request.judge_model,
        **call_kwargs,
    )
    return JSONResponse(content=result.to_dict())




@app.get("/v1/credits")
async def get_credits() -> dict[str, Any]:
    """Crediti residui per provider (quota free + budget paid)."""
    result = {}

    for pid, provider in state.config.free_providers.items():
        limits = provider.free_tier.limits if provider.free_tier else {}
        status = await state.quota_manager.get_status(
            pid,
            rpm_limit=limits.get("rpm"),
            rpd_limit=limits.get("rpd"),
            tpd_limit=limits.get("tokens_per_day"),
        )

        rpm_pct = 100.0
        if status.rpm_limit and status.rpm_limit > 0:
            rpm_pct = max(0.0, 100.0 * (status.rpm_limit - status.requests_this_minute) / status.rpm_limit)

        rpd_pct = 100.0
        if status.rpd_limit and status.rpd_limit > 0:
            rpd_pct = max(0.0, 100.0 * (status.rpd_limit - status.requests_today) / status.rpd_limit)

        result[pid] = {
            "name": provider.name,
            "type": "free",
            "available": status.is_available,
            "in_cooldown": status.is_in_cooldown,
            "cooldown_seconds": status.cooldown_remaining,
            "rpm_used": status.requests_this_minute,
            "rpm_limit": status.rpm_limit,
            "rpm_percent": round(rpm_pct, 1),
            "rpd_used": status.requests_today,
            "rpd_limit": status.rpd_limit,
            "rpd_percent": round(rpd_pct, 1),
            "tokens_today": status.tokens_today,
            "tpd_limit": status.tpd_limit,
        }

    for pid, provider in state.config.paid_providers.items():
        bp = state.config.budget.per_provider.get(pid)
        if bp:
            result[pid] = {
                "name": provider.name,
                "type": "paid",
                "available": True,
                "budget_month_usd": bp.monthly_budget_usd,
                "budget_used_usd": 0.0,
                "budget_remaining_usd": bp.monthly_budget_usd,
                "budget_percent": 100.0,
            }

    return result




# --- Endpoint multimodali ---------------------------------------------------

class ImageRequest(BaseModel):
    prompt: str
    width: int = 1024
    height: int = 1024
    model: str = "flux"


class VideoRequest(BaseModel):
    prompt: str
    model: str = "wan-fast"
    duration: int = 5


class MusicRequest(BaseModel):
    prompt: str
    title: str = ""


class TranslationRequest(BaseModel):
    text: str
    target_lang: str = "en"
    source_lang: str | None = None


@app.post("/v1/images/generations")
async def generate_image(request: ImageRequest) -> JSONResponse:
    """Genera un'immagine con Pollinations.ai."""
    result = await state.image_router.generate(
        prompt=request.prompt,
        width=request.width,
        height=request.height,
    )
    return JSONResponse(content=result.to_dict())


@app.post("/v1/videos")
async def generate_video(request: VideoRequest) -> JSONResponse:
    """Avvia la generazione di un video con InferencePort."""
    result = await state.video_generator.generate(
        prompt=request.prompt,
        duration=request.duration,
    )
    return JSONResponse(content=result.to_dict())


@app.get("/v1/videos/{job_id}")
async def get_video_status(job_id: str) -> JSONResponse:
    """Polling dello stato di un video."""
    result = await state.video_generator.poll(job_id)
    return JSONResponse(content=result.to_dict())


@app.post("/v1/audio/generations")
async def generate_music(request: MusicRequest) -> JSONResponse:
    """Genera una canzone con Tunova."""
    result = await state.music_generator.generate(
        prompt=request.prompt,
        title=request.title,
    )
    return JSONResponse(content=result.to_dict())


@app.get("/v1/audio/generations/{job_id}")
async def get_music_status(job_id: str) -> JSONResponse:
    """Polling dello stato di una canzone."""
    result = await state.music_generator.poll(job_id)
    return JSONResponse(content=result.to_dict())


@app.post("/v1/translations")
async def translate(request: TranslationRequest) -> JSONResponse:
    """Traduce un testo con Index-Translate."""
    result = await state.translator.translate(
        text=request.text,
        target_lang=request.target_lang,
        source_lang=request.source_lang,
    )
    return JSONResponse(content=result.to_dict())




@app.get("/v1/professions")
async def list_professions() -> JSONResponse:
    """Elenco dei profili professionali disponibili."""
    try:
        pm = get_profession_manager()
        return JSONResponse({"professions": pm.list_all()})
    except Exception as e:
        return JSONResponse({"professions": [], "error": str(e)})




# ============================================================
# FILE UPLOAD — Allegati
# ============================================================

@app.post("/v1/files/upload")
async def upload_file(file: UploadFile = File(...)) -> JSONResponse:
    """Riceve un file, estrae il testo, lo restituisce."""
    try:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:  # 20 MB
            raise HTTPException(status_code=413, detail="File troppo grande (max 20 MB)")

        result = read_file_bytes(file.filename or "file", data)
        return JSONResponse(content=result.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        log.error("sinfonia.upload_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Errore lettura file: {str(e)[:200]}")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=False)
