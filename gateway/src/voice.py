"""
Bro — Voice Module
STT con faster-whisper, TTS con Piper. Tutto locale.
"""

from __future__ import annotations

import io
import os
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import structlog

log = structlog.get_logger()

VOICES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "voices"
DEFAULT_VOICE = "it_IT-serena-medium.onnx"
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANG", "it")


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

    def transcribe_bytes(self, audio_bytes: bytes, language: str = WHISPER_LANGUAGE) -> TranscriptionResult:
        self._load_model()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        try:
            segments, info = self._model.transcribe(
                tmp_path, language=language, beam_size=5,
                vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return TranscriptionResult(
                text=text, language=info.language,
                duration_seconds=info.duration, is_empty=len(text) < 2,
            )
        finally:
            os.unlink(tmp_path)

    def transcribe_numpy(self, audio_array, sample_rate: int = 16000) -> TranscriptionResult:
        """Trascrive un array numpy float32 direttamente (bypassa PyAV/file)."""
        import numpy as np
        self._load_model()

        # Assicurati che sia float32 in [-1, 1]
        if audio_array.dtype != np.float32:
            audio_array = audio_array.astype(np.float32)
        audio_array = np.ascontiguousarray(audio_array)

        # Faster-whisper accetta direttamente array numpy -> niente PyAV, niente WAV
        segments, info = self._model.transcribe(
            audio_array,
            language=WHISPER_LANGUAGE,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return TranscriptionResult(
            text=text,
            language=info.language,
            duration_seconds=info.duration,
            is_empty=len(text) < 2,
        )


class TextToSpeech:
    """TTS con Piper — API 1.x (AudioChunk generator)."""

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
                # Fallback per versioni vecchie
                from piper.voice import PiperVoice
            log.info("voice.tts_loading", voice=str(self.voice_path))

            # Prova con config_path se disponibile
            if self.config_path.exists():
                self._piper_voice = PiperVoice.load(
                    str(self.voice_path),
                    config_path=str(self.config_path),
                )
            else:
                self._piper_voice = PiperVoice.load(str(self.voice_path))

            log.info("voice.tts_ready")

    def synthesize(self, text: str) -> bytes:
        """
        Genera WAV in bytes dal testo usando la nuova API AudioChunk.
        """
        if not self.is_available:
            raise FileNotFoundError(f"Voce Piper non trovata: {self.voice_path}")

        self._load_voice()

        # Nuova API piper-tts 1.x: synthesize() restituisce un generatore di AudioChunk
        sample_rate = 22050  # default
        sample_width = 2     # 16-bit
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
        """Sintetizza e riproduce direttamente."""
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


if __name__ == "__main__":
    print("=== Test STT ===")
    stt = get_stt()
    print(f"Modello: {stt.model_size}")
    print()
    print("=== Test TTS ===")
    tts = get_tts()
    print(f"Voce disponibile: {tts.is_available}")
    print(f"File: {tts.voice_path}")
    if tts.is_available:
        print()
        print("Generazione audio di test...")
        text = "Ciao Fabio, sono Doc. Il sistema vocale e operativo."
        try:
            wav = tts.synthesize(text)
            output_path = "/tmp/bro_test.wav"
            with open(output_path, "wb") as f:
                f.write(wav)
            print(f"OK: Salvato in {output_path} ({len(wav)} bytes)")
            print(f"Riproduci con: afplay {output_path}")
        except Exception as e:
            print(f"ERRORE: {e}")
