"""
Chatterbox TTS Server — micro-server FastAPI per Bro.
Usa mlx-audio (Blaizzy) con Chatterbox Multilingual (23 lingue).
Gira su porta 8081.
"""

from __future__ import annotations

import io
import os
import tempfile
import wave
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

log = structlog.get_logger()
app = FastAPI(title="Chatterbox TTS Server")

MODEL_ID = os.environ.get("CHATTERBOX_MODEL", "mlx-community/chatterbox-fp16")
_model = None


def get_model():
    global _model
    if _model is None:
        from mlx_audio.tts.utils import load_model
        log.info("chatterbox.loading", model=MODEL_ID)
        _model = load_model(MODEL_ID)
        log.info("chatterbox.ready", model=MODEL_ID)
    return _model


class TTSRequest(BaseModel):
    text: str
    language_id: str = "it"


def _wav_from_dir(tmpdir: Path, prefix: str) -> bytes:
    """Legge i file WAV generati da mlx-audio e li concatena."""
    files = sorted(tmpdir.glob(f"{prefix}*.wav"))
    if not files:
        raise FileNotFoundError(f"Nessun WAV generato in {tmpdir} con prefisso {prefix}")
    if len(files) == 1:
        return files[0].read_bytes()

    output = io.BytesIO()
    with wave.open(output, "wb") as out_wav:
        params_set = False
        for f in files:
            with wave.open(str(f), "rb") as in_wav:
                if not params_set:
                    out_wav.setnchannels(in_wav.getnchannels())
                    out_wav.setsampwidth(in_wav.getsampwidth())
                    out_wav.setframerate(in_wav.getframerate())
                    params_set = True
                out_wav.writeframes(in_wav.readframes(in_wav.getnframes()))
    return output.getvalue()


@app.post("/tts")
async def tts(request: TTSRequest) -> Response:
    try:
        from mlx_audio.tts.generate import generate_audio
        get_model()  # carica il modello (una tantum)

        with tempfile.TemporaryDirectory() as tmpdir:
            prefix = "out"
            generate_audio(
                text=request.text,
                model=MODEL_ID,
                lang_code=request.language_id,
                file_prefix=prefix,
                output_path=tmpdir,
            )
            wav_bytes = _wav_from_dir(Path(tmpdir), prefix)
            log.info("chatterbox.tts_ok", chars=len(request.text), bytes=len(wav_bytes))
            return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as e:
        log.error("chatterbox.tts_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "model": MODEL_ID, "engine": "mlx-audio"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8081)
