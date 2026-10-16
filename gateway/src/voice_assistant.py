"""
Bro — Voice Assistant Loop
Ascolta in continuazione, rileva "Ehi Doc", registra, trascrive, invia a Sinfonia, risponde a voce.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path
from typing import Callable

import httpx
import structlog

# Assicura che i moduli in gateway/src siano importabili
sys.path.insert(0, str(Path(__file__).resolve().parent))

log = structlog.get_logger()

SAMPLE_RATE = 16000
CHANNELS = 1
SILENCE_THRESHOLD = 0.025
SILENCE_DURATION = 1.5
MAX_RECORD_SECONDS = 15
SINFONIA_URL = "http://127.0.0.1:8080"


class VoiceAssistant:
    def __init__(self, on_state: Callable[[str], None] | None = None):
        self.on_state = on_state
        self._stt = None
        self._tts = None
        self._wake = None
        self._running = False
        self._conversation_id: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def stt(self):
        if self._stt is None:
            from voice import get_stt
            self._stt = get_stt()
        return self._stt

    @property
    def tts(self):
        if self._tts is None:
            from voice import get_tts
            self._tts = get_tts()
        return self._tts

    def _set_state(self, state: str):
        log.info("voice_assistant.state", state=state)
        if self.on_state:
            try:
                self.on_state(state)
            except Exception:
                pass

    def _record_until_silence(self):
        """Registra dal microfono fino a silenzio prolungato. Ritorna np.ndarray float32."""
        import numpy as np
        import sounddevice as sd

        log.info("voice_assistant.recording_start")
        audio_frames = []
        silence_frames = 0
        silence_limit = int(SILENCE_DURATION * SAMPLE_RATE / 1024)
        max_frames = int(MAX_RECORD_SECONDS * SAMPLE_RATE / 1024)
        started_speaking = False

        def callback(indata, frames, time_info, status):
            nonlocal audio_frames, silence_frames, started_speaking
            if status:
                return
            audio_frames.append(indata.copy())
            rms = float(np.sqrt(np.mean(indata ** 2)))
            if rms > SILENCE_THRESHOLD:
                started_speaking = True
                silence_frames = 0
            elif started_speaking:
                silence_frames += 1

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=1024,
            callback=callback,
        )
        stream.start()

        wait_frames = 0
        while not started_speaking and wait_frames < 200:
            time.sleep(0.05)
            wait_frames += 1

        if not started_speaking:
            stream.stop()
            stream.close()
            return None

        frames_count = 0
        while silence_frames < silence_limit and frames_count < max_frames:
            time.sleep(0.05)
            frames_count += 1

        stream.stop()
        stream.close()

        if not audio_frames:
            return None

        audio = np.concatenate(audio_frames, axis=0).flatten()
        duration = len(audio) / SAMPLE_RATE
        log.info("voice_assistant.recorded", duration=round(duration, 2))
        return audio

    async def _ask_sinfonia(self, text: str) -> str:
        log.info("voice_assistant.asking", text=text[:80])
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "model": "sinfonia/auto",
                "messages": [{"role": "user", "content": text}],
                "voice_mode": True,
            }
            if self._conversation_id:
                payload["conversation_id"] = self._conversation_id

            resp = await client.post(
                f"{SINFONIA_URL}/v1/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            self._conversation_id = data.get("conversation_id") or self._conversation_id
            return data["choices"][0]["message"]["content"]

    async def _interaction_loop(self):
        try:
            self._set_state("recording")
            audio_array = await asyncio.to_thread(self._record_until_silence)
            if audio_array is None or len(audio_array) == 0:
                self._set_state("idle")
                return

            self._set_state("transcribing")
            result = await asyncio.to_thread(
                self.stt.transcribe_numpy, audio_array, SAMPLE_RATE
            )
            if result.is_empty:
                log.info("voice_assistant.empty_transcription")
                self._set_state("idle")
                return

            text = result.text.strip()
            log.info("voice_assistant.transcribed", text=text)
            self._set_state("heard:" + text)

            self._set_state("thinking")
            response = await self._ask_sinfonia(text)
            log.info("voice_assistant.response", text=response[:100])
            self._set_state("response:" + response[:100])

            self._set_state("speaking")
            clean_text = self._clean_for_tts(response)
            log.info("voice_assistant.tts_clean", text=clean_text[:100])
            await asyncio.to_thread(self.tts.speak, clean_text)

        except Exception as e:
            log.error("voice_assistant.error", error=str(e))
        finally:
            self._set_state("idle")

    def _clean_for_tts(self, text: str) -> str:
        """Pulisce il testo per TTS rimuovendo markdown, LaTeX, intestazioni."""
        # Codice
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"`[^`]+`", "", text)
        # LaTeX
        text = re.sub(r"\$\$[\s\S]*?\$\$", "", text)
        text = re.sub(r"\$[^\$]+\$", "", text)
        # Intestazioni markdown
        text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
        # Grassetti/corsivi
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)
        # Link
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Tabelle
        text = re.sub(r"\|[^\n]+\|", "", text)
        # Liste puntate
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
        # Intestazioni testuali indesiderate
        for header in ["Dati", "Svolgimento", "Risultato finale", "Risultato", "Risposta", "Note", "Soluzione"]:
            text = re.sub(r"\b" + header + r"\s*:?\s*", "", text, flags=re.IGNORECASE)
        # Compatta
        text = re.sub(r"\n\s*\n", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 500:
            text = text[:500] + "..."
        return text

    def start(self):
        from wake_word import WakeWordListener

        if self._running:
            return
        self._running = True

        def on_wake():
            log.info("voice_assistant.wake_triggered")
            asyncio.run_coroutine_threadsafe(
                self._interaction_loop(),
                self._loop,
            )

        self._wake = WakeWordListener(on_wake=on_wake)
        self._wake.start()
        log.info("voice_assistant.started")

    def stop(self):
        self._running = False
        if self._wake:
            self._wake.stop()
        log.info("voice_assistant.stopped")

    def run_forever(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.start()
        log.info("voice_assistant.ready", hint="Di' 'Ehi Doc' per parlare")
        try:
            self._loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


if __name__ == "__main__":
    print("=== Bro Voice Assistant ===")
    print()
    print("Sistema operativo:")
    print("  1. Dì 'Ehi Doc' o 'Ehi Bro'")
    print("  2. Parla (verrà registrato)")
    print("  3. Smetti di parlare (rilevato silenzio automatico)")
    print("  4. Bro risponde a voce")
    print()
    print("Premi Ctrl+C per fermare")
    print()

    def on_state(state):
        print("  [" + state + "]")

    assistant = VoiceAssistant(on_state=on_state)
    assistant.run_forever()
