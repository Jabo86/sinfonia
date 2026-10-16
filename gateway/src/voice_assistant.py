"""
Bro — Voice Assistant Loop
Ascolta in continuazione, rileva "Ehi Doc", registra, trascrive, invia a Sinfonia, risponde a voce.
Supporta interazioni multiple consecutive.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Callable

import httpx
import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent))

log = structlog.get_logger()

SAMPLE_RATE = 16000
CHANNELS = 1
SILENCE_THRESHOLD = 0.022
SILENCE_DURATION = 1.2
MAX_RECORD_SECONDS = 15
SINFONIA_URL = "http://127.0.0.1:8080"
VOICE_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "voice_state.json"

# Modalità conversazione continua
CONVERSATION_WINDOW = 8.0    # secondi di ascolto attivo dopo ogni risposta
CONVERSATION_MAX_TURNS = 10  # max turni prima di tornare alla wake word


class VoiceAssistant:
    def __init__(self, on_state: Callable[[str], None] | None = None):
        self.on_state = on_state
        self._stt = None
        self._tts = None
        self._wake = None
        self._running = False
        self._conversation_id: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._interaction_lock = asyncio.Lock()

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
        try:
            import time as _t
            with open(VOICE_STATE_FILE, "w") as f:
                json.dump({"state": state, "timestamp": _t.time()}, f)
        except Exception:
            pass
        if self.on_state:
            try:
                self.on_state(state)
            except Exception:
                pass

    def _record_until_silence(self):
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
        """Loop conversazione: wake → risposta → finestra conversazione → altri turni → wake."""
        async with self._interaction_lock:
            try:
                if self._wake:
                    self._wake.pause()

                # Primo turno (dopo wake word)
                await self._do_one_turn(first_turn=True)

                # Turni di conversazione continua
                for turn in range(CONVERSATION_MAX_TURNS):
                    log.info("voice_assistant.conversation_window", turn=turn + 1)
                    self._set_state("listening")

                    # Ascolta fino a CONVERSATION_WINDOW secondi per un nuovo input
                    audio = await asyncio.to_thread(self._record_with_timeout, CONVERSATION_WINDOW)
                    if audio is None:
                        log.info("voice_assistant.conversation_end", reason="silence")
                        break

                    # Trascrivi
                    self._set_state("transcribing")
                    result = await asyncio.to_thread(
                        self.stt.transcribe_numpy, audio, SAMPLE_RATE
                    )
                    if result.is_empty or len(result.text.strip()) < 2:
                        log.info("voice_assistant.empty_turn")
                        break

                    text = result.text.strip()
                    log.info("voice_assistant.transcribed", text=text, turn=turn + 2)
                    self._set_state("heard:" + text)

                    # Chiedi a Sinfonia
                    self._set_state("thinking")
                    response = await self._ask_sinfonia(text)
                    log.info("voice_assistant.response", text=response[:100])

                    # Parla
                    self._set_state("speaking")
                    clean_text = self._clean_for_tts(response)
                    await asyncio.to_thread(self.tts.speak, clean_text)

            except Exception as e:
                log.error("voice_assistant.error", error=str(e))
            finally:
                self._set_state("idle")
                await asyncio.sleep(0.5)
                if self._wake:
                    self._wake.resume()
                log.info("voice_assistant.ready_for_wake_word")

    async def _do_one_turn(self, first_turn: bool = False):
        """Registra, trascrive, chiede a Sinfonia, parla."""
        self._set_state("recording")
        audio_array = await asyncio.to_thread(self._record_until_silence)
        if audio_array is None or len(audio_array) == 0:
            log.info("voice_assistant.no_audio")
            return

        self._set_state("transcribing")
        result = await asyncio.to_thread(
            self.stt.transcribe_numpy, audio_array, SAMPLE_RATE
        )
        if result.is_empty:
            log.info("voice_assistant.empty_transcription")
            return

        text = result.text.strip()
        log.info("voice_assistant.transcribed", text=text)
        self._set_state("heard:" + text)

        self._set_state("thinking")
        response = await self._ask_sinfonia(text)
        log.info("voice_assistant.response", text=response[:100])

        self._set_state("speaking")
        clean_text = self._clean_for_tts(response)
        await asyncio.to_thread(self.tts.speak, clean_text)

    def _record_with_timeout(self, timeout_seconds: float):
        """
        Registra per un tempo massimo (finestra di conversazione).
        Ritorna None se non sente nulla, altrimenti l'audio.
        """
        import numpy as np
        import sounddevice as sd

        log.info("voice_assistant.window_start", timeout=timeout_seconds)
        audio_frames = []
        silence_frames = 0
        started_speaking = False
        silence_limit = int(SILENCE_DURATION * SAMPLE_RATE / 1024)
        max_frames = int(timeout_seconds * SAMPLE_RATE / 1024)

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

        frames_count = 0
        while frames_count < max_frames:
            time.sleep(0.05)
            frames_count += 1
            # Se ha iniziato a parlare e poi ha smesso, esci
            if started_speaking and silence_frames >= silence_limit:
                break

        stream.stop()
        stream.close()

        # Se non ha mai parlato, ritorna None (finestra scaduta silenziosamente)
        if not started_speaking:
            log.info("voice_assistant.window_expired")
            return None

        if not audio_frames:
            return None

        audio = np.concatenate(audio_frames, axis=0).flatten()
        # Rimuovi i primi frame di silenzio (prima che iniziasse a parlare)
        duration = len(audio) / SAMPLE_RATE
        log.info("voice_assistant.window_recorded", duration=round(duration, 2))
        return audio


    def _clean_for_tts(self, text: str) -> str:
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"`[^`]+`", "", text)
        text = re.sub(r"\$\$[\s\S]*?\$\$", "", text)
        text = re.sub(r"\$[^\$]+\$", "", text)
        text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"\|[^\n]+\|", "", text)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
        for header in ["Dati", "Svolgimento", "Risultato finale", "Risultato", "Risposta", "Note", "Soluzione"]:
            text = re.sub(r"\b" + header + r"\s*:?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n\s*\n", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 2000:
            text = text[:2000] + "..."
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
    print("1. Dì 'Ehi Doc' o 'Ehi Bro'")
    print("2. Parla")
    print("3. Smetti di parlare")
    print("4. Bro risponde a voce")
    print("5. RIPETI — puoi fare quante domande vuoi!")
    print()
    print("Premi Ctrl+C per fermare")
    print()

    def on_state(state):
        print("  [" + state + "]")

    assistant = VoiceAssistant(on_state=on_state)
    assistant.run_forever()
