"""
Bro — Voice API
Endpoint FastAPI per STT e TTS.
"""

from __future__ import annotations

import base64
import io
import wave

import structlog
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

log = structlog.get_logger()
router = APIRouter(prefix="/v1/voice", tags=["voice"])


class SpeakRequest(BaseModel):
    text: str
    speed: float = 1.0


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> JSONResponse:
    """Trascrive un file audio (WAV/WebM/OGG) in testo."""
    try:
        from voice import get_stt
        audio_bytes = await file.read()
        stt = get_stt()
        result = stt.transcribe_bytes(audio_bytes)
        log.info("voice_api.transcribed", text=result.text[:80], duration=result.duration_seconds)
        return JSONResponse({
            "text": result.text,
            "language": result.language,
            "duration": result.duration_seconds,
            "is_empty": result.is_empty,
        })
    except Exception as e:
        log.error("voice_api.transcribe_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Errore trascrizione: {e}")


@router.post("/speak")
async def speak(request: SpeakRequest) -> Response:
    """Genera WAV dal testo e lo restituisce."""
    try:
        from voice import get_tts
        tts = get_tts()
        wav_bytes = tts.synthesize(request.text)
        log.info("voice_api.spoken", text=request.text[:80], bytes=len(wav_bytes))
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={"Content-Length": str(len(wav_bytes))},
        )
    except Exception as e:
        log.error("voice_api.speak_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Errore sintesi: {e}")


@router.get("/status")
async def voice_status() -> JSONResponse:
    """Verifica se STT e TTS sono disponibili."""
    try:
        from voice import get_tts
        tts = get_tts()
        return JSONResponse({
            "tts_available": tts.is_available,
            "voice_file": str(tts.voice_path),
            "stt_model": "faster-whisper base",
        })
    except Exception as e:
        return JSONResponse({"tts_available": False, "error": str(e)})

@router.get("/state")
async def voice_state() -> JSONResponse:
    """Stato corrente del voice assistant (per la UI)."""
    import json
    import time
    from pathlib import Path
    state_file = Path(__file__).resolve().parent.parent.parent / "data" / "voice_state.json"
    try:
        if state_file.exists():
            with open(state_file) as f:
                data = json.load(f)
            # Se lo stato è più vecchio di 10 secondi, considera idle
            age = time.time() - data.get("timestamp", 0)
            if age > 10:
                return JSONResponse({"state": "idle", "age": age})
            return JSONResponse(data)
    except Exception:
        pass
    return JSONResponse({"state": "idle"})
