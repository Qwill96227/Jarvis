"""Always-on wake word ("Hey Jarvis") with openWakeWord, running locally on the CPU.

Audio is analysed in 80 ms frames and never stored or sent anywhere. Pretrained phrases
are downloaded once (a few MB) to %APPDATA%\\Jarvis\\wakeword. A custom phrase such as
"Hey Drexya" can be trained with openWakeWord's notebook; set wake_word to the .onnx path.
"""
import threading
import time
from pathlib import Path

import numpy as np

from . import config

FRAME = 1280                # 80 ms at 16 kHz, what openWakeWord expects
RATE = 16000
COOLDOWN = 2.0              # seconds before the same phrase can trigger again
PRETRAINED = {              # setting value -> openWakeWord model name
    "hey_jarvis": "hey_jarvis_v0.1",
    "alexa": "alexa_v0.1",
    "hey_mycroft": "hey_mycroft_v0.1",
}
SPOKEN = {"hey_jarvis": "Hey Jarvis", "alexa": "Alexa", "hey_mycroft": "Hey Mycroft"}


def phrase(wake_word: str) -> str:
    """How to say it, for the status line: 'Hey Jarvis', or 'hey drexya' for hey_drexya.onnx."""
    return SPOKEN.get(wake_word) or Path(wake_word).stem.replace("_", " ")


def model_paths(wake_word: str) -> dict:
    """Download (first time) and return the model files for a pretrained or custom wake word."""
    from openwakeword import utils
    folder = config.WAKEWORD_DIR
    custom = Path(wake_word)
    if custom.suffix == ".onnx":
        if not custom.exists():
            raise FileNotFoundError(f"Wake word model not found: {custom}")
        utils.download_models([], target_directory=str(folder))  # still needs the shared feature models
        word = custom
    else:
        name = PRETRAINED.get(wake_word, PRETRAINED["hey_jarvis"])
        word = folder / f"{name}.onnx"
        if not word.exists():
            utils.download_models([name], target_directory=str(folder))
    return {"wakeword_models": [str(word)], "melspec_model_path": str(folder / "melspectrogram.onnx"),
            "embedding_model_path": str(folder / "embedding_model.onnx")}


class WakeListener:
    """Listens on the default mic in a background thread and calls on_wake() (from that
    thread) when the phrase is heard. pause() while Drexya is recording you."""

    def __init__(self, wake_word: str, threshold: float, on_wake):
        self.wake_word, self.threshold, self.on_wake = wake_word, threshold, on_wake
        self.error = None
        self._paused = threading.Event()
        self._stopped = threading.Event()
        self._last = 0.0

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def stop(self):
        self._stopped.set()

    def _run(self):
        try:
            import sounddevice as sd
            from openwakeword.model import Model
            model = Model(inference_framework="onnx", **model_paths(self.wake_word))
            with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME) as stream:
                was_paused = False
                while not self._stopped.is_set():
                    frame, _ = stream.read(FRAME)
                    if self._paused.is_set():
                        was_paused = True
                        continue
                    if was_paused:  # don't let audio from before the pause trigger it
                        model.reset()
                        was_paused = False
                    score = max(model.predict(frame[:, 0]).values())
                    if score >= self.threshold and time.monotonic() - self._last > COOLDOWN:
                        self._last = time.monotonic()
                        model.reset()
                        self.on_wake()
        except Exception as e:
            self.error = e
            print(f"[wakeword] stopped: {e}")


class EndOfSpeech:
    """Decides when a hands-free request is over: about a second of quiet after speech,
    nothing said at all for a few seconds, or a hard cap. Feed it each audio chunk."""

    END_SILENCE = 1.2   # seconds of quiet after speaking
    NO_SPEECH = 5.0     # give up if nothing is said
    MAX_LENGTH = 20.0

    def __init__(self):
        self.floor = None   # running estimate of background noise
        self.heard = False
        self.quiet = 0.0
        self.elapsed = 0.0

    def feed(self, chunk: np.ndarray) -> bool:
        """chunk: float32 samples at 16 kHz. Returns True once listening should stop."""
        dur = len(chunk) / RATE
        rms = float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64)))) if len(chunk) else 0.0
        self.elapsed += dur
        # Track the noise floor: drop quickly to quieter levels, creep up slowly
        self.floor = rms if self.floor is None else min(rms, self.floor * 1.002 + 1e-6)
        if rms > max(self.floor * 3, 0.01):
            self.heard, self.quiet = True, 0.0
        else:
            self.quiet += dur
        return ((self.heard and self.quiet >= self.END_SILENCE)
                or (not self.heard and self.elapsed >= self.NO_SPEECH)
                or self.elapsed >= self.MAX_LENGTH)
