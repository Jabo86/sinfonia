"""
Bro — Voice Module
STT con faster-whisper (base + initial_prompt tecnico), TTS con Piper.
"""

from __future__ import annotations

import io
import os
import wave
from dataclasses import dataclass
from pathlib import Path

import structlog

log = structlog.get_logger()

VOICES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "voices"
DEFAULT_VOICE = "it_IT-serena-medium.onnx"
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANG", "it")

# Prompt molto ricco: aiuta base a riconoscere termini tecnici e nomi
WHISPER_INITIAL_PROMPT = (
    "Questa è una conversazione in italiano. L'utente parla con un assistente vocale. "
    "Argomenti comuni: medicina, anatomia, cuore, ventricoli, atri, arterie, vene, "
    "sistema circolatorio, sistole, diastole, ossigeno, sangue, tessuti, valvole, "
    "capillari, fotosintesi, clorofilla, scienza, fisica, matematica, storia, "
    "geografia, cucina, ricette, tecnologia, programmazione. "
    "Frasi di esempio: che giorno è oggi, che ore sono, che tempo fa, "
    "come funziona il cuore, spiegami la fotosintesi, raccontami la storia di Roma."
)


@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration_seconds: float
    is_empty: bool


class SpeechToText:
    def __init__(self, model_size: str = WHISPER_MODEL_SIZE):
        self.model_size = model_size
        self._model = None

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            log.info("voice.stt_loading", model=self.model_size)
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            log.info("voice.stt_ready", model=self.model_size)

    def transcribe_numpy(self, audio_array, sample_rate: int = 16000) -> TranscriptionResult:
        import numpy as np
        self._load_model()
        if audio_array.dtype != np.float32:
            audio_array = audio_array.astype(np.float32)
        audio_array = np.ascontiguousarray(audio_array)

        segments, info = self._model.transcribe(
            audio_array,
            language=WHISPER_LANGUAGE,
            beam_size=5,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=False,
            initial_prompt=WHISPER_INITIAL_PROMPT,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        log.info("voice.transcribed", text=text, duration=round(info.duration, 2))
        return TranscriptionResult(
            text=text, language=info.language,
            duration_seconds=info.duration, is_empty=len(text) < 2,
        )


class TextToSpeech:
    """TTS con Chatterbox Multilingual (server 8081) + Piper fallback."""

    CHATTERBOX_URL = "http://127.0.0.1:8081/tts"

    def __init__(self, voice_file: str = DEFAULT_VOICE):
        self.voice_path = VOICES_DIR / voice_file
        self.config_path = Path(str(self.voice_path) + ".json")
        self._piper_voice = None
        self._chatterbox_checked = False
        self._chatterbox_ok = False

    @property
    def is_available(self) -> bool:
        return True  # Piper come fallback è sempre disponibile

    def _check_chatterbox(self) -> bool:
        if self._chatterbox_checked:
            return self._chatterbox_ok
        self._chatterbox_checked = True
        try:
            import httpx
            r = httpx.get("http://127.0.0.1:8081/health", timeout=2.0)
            self._chatterbox_ok = (r.status_code == 200)
            if self._chatterbox_ok:
                log.info("voice.chatterbox_available")
            else:
                log.info("voice.chatterbox_unavailable", status=r.status_code)
        except Exception as e:
            log.info("voice.chatterbox_unavailable", error=str(e)[:80])
            self._chatterbox_ok = False
        return self._chatterbox_ok

    def synthesize(self, text: str) -> bytes:
        # Prova Chatterbox
        if self._check_chatterbox():
            try:
                import httpx
                r = httpx.post(
                    self.CHATTERBOX_URL,
                    json={"text": text[:500], "language_id": "it"},
                    timeout=180.0,
                )
                if r.status_code == 200 and len(r.content) > 1000:
                    log.info("voice.tts_chatterbox", chars=len(text), bytes=len(r.content))
                    return r.content
                log.warning("voice.chatterbox_bad_response", status=r.status_code, bytes=len(r.content))
            except Exception as e:
                log.warning("voice.chatterbox_error", error=str(e)[:80])

        # Fallback a Piper
        log.info("voice.tts_piper_fallback")
        return self._piper_synthesize(text)

    def _piper_synthesize(self, text: str) -> bytes:
        if not self.voice_path.exists():
            raise FileNotFoundError(f"Voce Piper non trovata: {self.voice_path}")
        if self._piper_voice is None:
            try:
                from piper import PiperVoice
            except ImportError:
                from piper.voice import PiperVoice
            log.info("voice.tts_loading_piper", voice=str(self.voice_path))
            if self.config_path.exists():
                self._piper_voice = PiperVoice.load(str(self.voice_path), config_path=str(self.config_path))
            else:
                self._piper_voice = PiperVoice.load(str(self.voice_path))
            log.info("voice.tts_ready_piper")

        sample_rate = 22050
        sample_width = 2
        frames = bytearray()
        for chunk in self._piper_voice.synthesize(text):
            sample_rate = chunk.sample_rate
            sample_width = chunk.sample_width
            frames.extend(chunk.audio_int16_bytes)
        if not frames:
            raise RuntimeError("Piper non ha generato audio")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(bytes(frames))
        return buf.getvalue()

    def speak(self, text: str) -> None:
        import sounddevice as sd
        import soundfile as sf
        wav_bytes = self.synthesize(text)
        with io.BytesIO(wav_bytes) as buf:
            audio, sr = sf.read(buf)
            sd.play(audio, sr)
            sd.wait()


_stt = None
_tts = None


def get_stt() -> SpeechToText:
    global _stt
    if _stt is None:
        _stt = SpeechToText()
    return _stt


def get_tts() -> TextToSpeech:
    global _tts
    if _tts is None:
        _tts = TextToSpeech()
    return _tts
