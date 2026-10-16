"""
Bro — Wake Word con stream dinamico.
Lo stream audio viene chiuso in pausa e riaperto al resume,
evitando conflitti con la registrazione.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Callable

import structlog

log = structlog.get_logger()

VOSK_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "vosk" / "vosk-model-small-it-0.4"

WAKE_WORDS = [
    "ehi doc", "ei doc", "hey doc",
    "ehi bro", "ei bro", "hey bro",
    "ehi sinfonia", "ok doc", "ok bro",
]


class WakeWordListener:
    def __init__(self, on_wake: Callable[[], None] | None = None):
        self.on_wake = on_wake
        self._running = False
        self._paused = False
        self._thread: threading.Thread | None = None
        self._model = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._cooldown_until = 0
        self._lock = threading.Lock()

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
            return
        if self._paused:
            return
        try:
            self._audio_queue.put_nowait(bytes(indata))
        except queue.Full:
            pass

    def _drain_queue(self):
        count = 0
        while True:
            try:
                self._audio_queue.get_nowait()
                count += 1
            except queue.Empty:
                break
        return count

    def _listen_loop(self):
        import sounddevice as sd
        from vosk import KaldiRecognizer

        self._load_model()
        log.info("wake.listening", wake_words=WAKE_WORDS)

        while self._running:
            # Se in pausa, dormi senza stream aperto
            if self._paused:
                time.sleep(0.1)
                continue

            # Apri lo stream audio
            try:
                with sd.RawInputStream(
                    samplerate=16000,
                    blocksize=8000,
                    dtype="int16",
                    channels=1,
                    callback=self._audio_callback,
                ):
                    rec = KaldiRecognizer(self._model, 16000)
                    rec.SetWords(False)
                    # Svuota coda residua
                    self._drain_queue()
                    log.info("wake.stream_open")

                    # Loop interno: leggi dal device finché non entriamo in pausa
                    while self._running and not self._paused:
                        try:
                            data = self._audio_queue.get(timeout=0.5)
                        except queue.Empty:
                            continue

                        if self._paused:
                            break

                        try:
                            if rec.AcceptWaveform(data):
                                result = json.loads(rec.Result())
                                text = result.get("text", "").lower().strip()
                                if not text:
                                    continue

                                now = time.time()
                                if now < self._cooldown_until:
                                    continue

                                for wake in WAKE_WORDS:
                                    if wake in text:
                                        log.info("wake.detected", wake=wake, full_text=text)
                                        self._cooldown_until = now + 3.0
                                        if self.on_wake:
                                            try:
                                                self.on_wake()
                                            except Exception as e:
                                                log.error("wake.callback_error", error=str(e))
                                        break
                        except Exception as e:
                            log.error("wake.recognize_error", error=str(e))
                            break

                    log.info("wake.stream_close")

            except Exception as e:
                log.error("wake.stream_error", error=str(e))
                time.sleep(0.5)

            # Svuota coda prima di riaprire
            self._drain_queue()
            # Piccola pausa per stabilizzare il device
            time.sleep(0.2)

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

    def pause(self):
        with self._lock:
            self._paused = True
            self._drain_queue()
        # Attendi che lo stream sia effettivamente chiuso
        time.sleep(0.3)
        log.info("wake.paused")

    def resume(self):
        with self._lock:
            self._drain_queue()
            self._paused = False
            self._cooldown_until = time.time() + 1.5
        # Attendi che lo stream sia riaperto
        time.sleep(0.3)
        log.info("wake.resumed")

    @property
    def is_running(self) -> bool:
        return self._running and not self._paused


if __name__ == "__main__":
    print("=== Test Wake Word (multi-interazione) ===")
    counter = [0]

    def on_wake():
        counter[0] += 1
        print(f"\n🎤 WAKE WORD #{counter[0]} RILEVATA!\n")
        # Simula registrazione
        print("   [simulo registrazione 3 sec...]")
        listener.pause()
        time.sleep(3)
        listener.resume()
        print("   [riprende ascolto...]\n")

    listener = WakeWordListener(on_wake=on_wake)
    try:
        listener.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nArresto...")
        listener.stop()
