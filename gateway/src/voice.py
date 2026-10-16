"""Bro — Voice Module: STT faster-whisper + TTS Piper."""
from __future__ import annotations
import io, os, wave
from dataclasses import dataclass
from pathlib import Path
import structlog

log = structlog.get_logger()
VOICES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "voices"
DEFAULT_VOICE = "it_IT-serena-medium.onnx"
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANG", "it")
WHISPER_INITIAL_PROMPT = "Conversazione in italiano. Argomenti: medicina, scienza, cucina, tecnologia."

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
            log.info("voice.stt_ready")
    def transcribe_numpy(self, audio_array, sample_rate: int = 16000) -> TranscriptionResult:
        import numpy as np
        self._load_model()
        if audio_array.dtype != np.float32:
            audio_array = audio_array.astype(np.float32)
        audio_array = np.ascontiguousarray(audio_array)
        segments, info = self._model.transcribe(
            audio_array, language=WHISPER_LANGUAGE, beam_size=5,
            temperature=0.0, condition_on_previous_text=False,
            initial_prompt=WHISPER_INITIAL_PROMPT, vad_filter=True,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        log.info("voice.transcribed", text=text[:80])
        return TranscriptionResult(text=text, language=info.language,
            duration_seconds=info.duration, is_empty=len(text) < 2)

class TextToSpeech:
    def __init__(self, voice_file: str = DEFAULT_VOICE):
        self.voice_path = VOICES_DIR / voice_file
        self.config_path = Path(str(self.voice_path) + ".json")
        self._piper_voice = None
    @property
    def is_available(self) -> bool:
        return self.voice_path.exists()
    def _load_voice(self):
        if self._piper_voice is None:
            try:
                from piper import PiperVoice
            except ImportError:
                from piper.voice import PiperVoice
            if self.config_path.exists():
                self._piper_voice = PiperVoice.load(str(self.voice_path), config_path=str(self.config_path))
            else:
                self._piper_voice = PiperVoice.load(str(self.voice_path))
    def synthesize(self, text: str) -> bytes:
        if not self.is_available:
            raise FileNotFoundError(f"Voce Piper non trovata: {self.voice_path}")
        self._load_voice()
        sample_rate, sample_width = 22050, 2
        frames = bytearray()
        for chunk in self._piper_voice.synthesize(text):
            sample_rate = chunk.sample_rate
            sample_width = chunk.sample_width
            frames.extend(chunk.audio_int16_bytes)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(sample_width); wf.setframerate(sample_rate)
            wf.writeframes(bytes(frames))
        return buf.getvalue()
    def speak(self, text: str) -> None:
        import sounddevice as sd, soundfile as sf
        wav_bytes = self.synthesize(text)
        with io.BytesIO(wav_bytes) as buf:
            audio, sr = sf.read(buf)
            sd.play(audio, sr); sd.wait()

_stt = None; _tts = None
def get_stt() -> SpeechToText:
    global _stt
    if _stt is None: _stt = SpeechToText()
    return _stt
def get_tts() -> TextToSpeech:
    global _tts
    if _tts is None: _tts = TextToText() if False else TextToSpeech()
    return _tts
