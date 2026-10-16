"""
Bro — Wake Word + Ascolto Continuo
Rileva "Ehi Doc" / "Ehi Bro" e attiva la trascrizione.
Tutto locale con Vosk.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from pathlib import Path
from typing import Callable

import structlog

log = structlog.get_logger()

VOSK_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "vosk" / "vosk-model-small-it-0.4"

# Wake word riconosciute (Vosk trascrive foneticamente)
WAKE_WORDS = [
    "ehi doc", "ei doc", "hey doc",
    "ehi bro", "ei bro", "hey bro",
    "ehi sinfonia", "ok doc", "ok bro",
]


class WakeWordListener:
    """Ascolta il microfono in continuazione e rileva la wake word."""

    def __init__(self, on_wake: Callable[[], None] | None = None):
        self.on_wake = on_wake
        self._running = False
        self._thread: threading.Thread | None = None
        self._model = None
        self._recognizer = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._wake_detected = False
        self._cooldown_until = 0

    def _load_model(self):
        if self._model is None:
            from vosk import Model
            if not VOSK_MODEL_PATH.exists():
                raise FileNotFoundError(f"Modello Vosk non trovato: {VOSK_MODEL_PATH}")
            log.info("wake.model_loading", path=str(VOSK_MODEL_PATH))
            self._model = Model(str(VOSK_MODEL_PATH))
            log.info("wake.model_ready")

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            log.warning("wake.audio_status", status=str(status))
        self._audio_queue.put(bytes(indata))

    def _listen_loop(self):
        """Loop di ascolto (gira in un thread separato)."""
        import sounddevice as sd
        from vosk import KaldiRecognizer

        self._load_model()
        rec = KaldiRecognizer(self._model, 16000)
        rec.SetWords(False)

        log.info("wake.listening", wake_words=WAKE_WORDS)

        with sd.RawInputStream(
            samplerate=16000,
            blocksize=8000,
            dtype="int16",
            channels=1,
            callback=self._audio_callback,
        ):
            while self._running:
                try:
                    data = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").lower().strip()
                    if not text:
                        continue

                    # Rileva wake word
                    now = time.time()
                    if now < self._cooldown_until:
                        continue

                    for wake in WAKE_WORDS:
                        if wake in text:
                            log.info("wake.detected", wake=wake, full_text=text)
                            self._wake_detected = True
                            self._cooldown_until = now + 3.0  # 3s di cooldown
                            if self.on_wake:
                                try:
                                    self.on_wake()
                                except Exception as e:
                                    log.error("wake.callback_error", error=str(e))
                            break

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        log.info("wake.started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        log.info("wake.stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def wake_detected(self) -> bool:
        w = self._wake_detected
        self._wake_detected = False
        return w


# === Test standalone ===
if __name__ == "__main__":
    print("=== Test Wake Word ===")
    print(f"Modello: {VOSK_MODEL_PATH}")
    print(f"Modello esiste: {VOSK_MODEL_PATH.exists()}")
    print(f"Wake words: {WAKE_WORDS}")
    print()
    print("Ascolto in corso... di' 'Ehi Doc' o 'Ehi Bro'")
    print("Premi Ctrl+C per fermare")
    print()

    def on_wake():
        print("🎤 WAKE WORD RILEVATA! (adesso parleresti)")

    listener = WakeWordListener(on_wake=on_wake)
    try:
        listener.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nArresto...")
        listener.stop()
