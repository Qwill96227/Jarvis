"""Ears (mic + Whisper) and mouth (Piper, with Windows' built-in voice as a fallback).
Everything here runs locally; only the transcribed text goes to Claude."""
import io
import re
import threading
import time
import wave

import numpy as np
import requests
import sounddevice as sd

from . import config

SAMPLE_RATE = 16000


# ---------------------------------------------------------------- ears
class Recorder:
    def __init__(self):
        self._chunks = []
        self._stream = None

    @property
    def recording(self):
        return self._stream is not None

    def start(self, on_end=None):
        """Start recording. With on_end, it's hands-free: on_end() is called once (from the
        audio thread) when the user stops talking; the caller then calls stop()."""
        from .wakeword import EndOfSpeech
        self._chunks = []
        detector = EndOfSpeech() if on_end else None
        ended = False

        def callback(data, frames, t, status):
            nonlocal ended
            self._chunks.append(data.copy())
            if detector and not ended and detector.feed(data[:, 0]):
                ended = True
                on_end()

        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback)
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is None:
            return np.zeros(0, dtype=np.float32)
        self._stream.stop()
        self._stream.close()
        self._stream = None
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._chunks).flatten()


class Transcriber:
    """Loads Whisper in the background so the window opens instantly.
    First launch downloads the model (~140 MB for base.en)."""

    def __init__(self, model_size: str):
        self.model = None
        self.error = None
        self._ready = threading.Event()
        threading.Thread(target=self._load, args=(model_size,), daemon=True).start()

    def _load(self, model_size):
        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        except Exception as e:
            self.error = e
        finally:
            self._ready.set()

    @property
    def ready(self):
        return self._ready.is_set() and self.model is not None

    def transcribe(self, audio: np.ndarray) -> str:
        self._ready.wait()
        if self.model is None:
            raise RuntimeError(f"Speech model failed to load: {self.error}")
        if audio.size < SAMPLE_RATE * 0.3:  # under 0.3s = accidental click
            return ""
        segments, _ = self.model.transcribe(audio, language="en", beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()


# ---------------------------------------------------------------- mouth
def _voice_urls(name: str):
    # en_GB-alan-medium -> en/en_GB/alan/medium/en_GB-alan-medium.onnx
    lang, speaker, quality = name.split("-")
    base = (f"https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            f"{lang.split('_')[0]}/{lang}/{speaker}/{quality}/{name}")
    return base + ".onnx", base + ".onnx.json"


def _clean_for_speech(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_`#>\[\]]", "", text)
    return text.strip()


class Speaker:
    def __init__(self, voice_name: str):
        self.voice_name = voice_name
        self.piper = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        threading.Thread(target=self._load_piper, daemon=True).start()

    def _load_piper(self):
        try:
            from piper import PiperVoice
            config.VOICES_DIR.mkdir(parents=True, exist_ok=True)
            onnx = config.VOICES_DIR / f"{self.voice_name}.onnx"
            meta = config.VOICES_DIR / f"{self.voice_name}.onnx.json"
            if not (onnx.exists() and meta.exists()):
                for url, dest in zip(_voice_urls(self.voice_name), (onnx, meta)):
                    r = requests.get(url, timeout=120)
                    r.raise_for_status()
                    dest.write_bytes(r.content)
            self.piper = PiperVoice.load(str(onnx), config_path=str(meta))
        except Exception as e:
            print(f"[voice] Piper unavailable, using Windows voice instead: {e}")
            self.piper = None

    def stop(self):
        self._stop.set()
        try:
            sd.stop()
        except Exception:
            pass

    def say(self, text: str):
        """Blocking. Call from a worker thread."""
        text = _clean_for_speech(text)
        if not text:
            return
        self._stop.clear()
        with self._lock:
            if self.piper is not None:
                try:
                    self._say_piper(text)
                    return
                except Exception as e:
                    print(f"[voice] Piper failed, falling back: {e}")
            self._say_sapi(text)

    def _say_piper(self, text):
        # Synthesize the whole reply into one buffer and play it once: a separate
        # play() per sentence left audible gaps and crackles between them.
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            self.piper.synthesize_wav(text, wf)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        # ~300 ms of trailing silence so the output device doesn't clip the last word
        audio = np.concatenate([audio, np.zeros(int(rate * 0.3), dtype=np.int16)])
        if self._stop.is_set():
            return
        sd.play(audio, rate, blocking=False, latency="high")
        while sd.get_stream().active:
            if self._stop.is_set():  # Stop button
                sd.stop()
                return
            time.sleep(0.05)

    def _say_sapi(self, text):
        import pyttsx3
        engine = pyttsx3.init()
        # Prefer a male voice if Windows has one (David), else default
        for v in engine.getProperty("voices"):
            if "david" in v.name.lower():
                engine.setProperty("voice", v.id)
                break
        engine.setProperty("rate", 185)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
