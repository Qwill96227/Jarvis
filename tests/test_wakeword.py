import io
import os
import unittest
import wave
from unittest import mock

import numpy as np

from jarvis import config, wakeword
from jarvis.app import JarvisApp
from jarvis.wakeword import EndOfSpeech

RATE = 16000
CHUNK = 1600  # 100 ms


def run_until_stop(chunks):
    eos = EndOfSpeech()
    for i, c in enumerate(chunks):
        if eos.feed(c):
            return (i + 1) * CHUNK / RATE
    return None


def noise(level, seconds, seed=0):
    rng = np.random.default_rng(seed)
    return [rng.normal(0, level, CHUNK).astype(np.float32) for _ in range(int(seconds * 10))]


def speech(seconds, seed=0):
    """Talking: loud syllables with short near-silent gaps between them, like real speech."""
    rng = np.random.default_rng(seed)
    return [rng.normal(0, 0.1 if i % 4 else 0.004, CHUNK).astype(np.float32) for i in range(int(seconds * 10))]


class EndOfSpeechTests(unittest.TestCase):
    def test_stops_about_a_second_after_speech(self):
        stopped = run_until_stop(noise(0.002, 0.5) + speech(2.0, 1) + noise(0.002, 5, 2))
        self.assertAlmostEqual(stopped, 0.5 + 2.0 + 1.2, delta=0.25)

    def test_talking_straight_after_the_wake_word(self):
        # no quiet moment first: the noise floor has to settle from the gaps between syllables
        stopped = run_until_stop(speech(3.0) + noise(0.002, 5, 2))
        self.assertAlmostEqual(stopped, 3.0 + 1.2, delta=0.25)

    def test_gives_up_if_nothing_said(self):
        self.assertAlmostEqual(run_until_stop(noise(0.002, 10)), 5.0, delta=0.15)

    def test_steady_background_noise_is_not_speech(self):
        # a fan or AC: constant moderate noise should count as the floor, not as talking
        self.assertAlmostEqual(run_until_stop(noise(0.02, 10)), 5.0, delta=0.15)

    def test_hard_cap(self):
        self.assertAlmostEqual(run_until_stop(speech(30)), 20.0, delta=0.15)


class PhraseTests(unittest.TestCase):
    def test_phrases(self):
        self.assertEqual(wakeword.phrase("hey_jarvis"), "Hey Jarvis")
        self.assertEqual(wakeword.phrase(r"C:\models\hey_drexya.onnx"), "hey drexya")

    def test_missing_custom_model(self):
        with self.assertRaises(FileNotFoundError):
            wakeword.model_paths(r"C:\nowhere\hey_drexya.onnx")


def fake_app(speaking=False, busy=False, recording=False):
    app = JarvisApp.__new__(JarvisApp)  # skip the real window and models
    app.speaking, app.busy, app.confirming = speaking, busy, False
    app.recorder = mock.Mock(recording=recording)
    app.recorder.stop.return_value = np.zeros(10, dtype=np.float32)
    app.speaker, app.wake = mock.Mock(), mock.Mock()
    app.ui = lambda fn, *a: fn(*a)
    app._set_state = mock.Mock()
    app._append = mock.Mock()
    return app


class InterruptionTests(unittest.TestCase):
    def test_wake_word_while_speaking_interrupts_and_listens_hands_free(self):
        app = fake_app(speaking=True, busy=True)
        app._on_wake()
        app.speaker.stop.assert_called_once()
        self.assertIsNotNone(app.recorder.start.call_args.kwargs["on_end"])
        app.wake.pause.assert_called_once()

    def test_click_while_speaking_interrupts(self):
        app = fake_app(speaking=True, busy=True)
        app.toggle_listen()
        app.speaker.stop.assert_called_once()
        self.assertIsNone(app.recorder.start.call_args.kwargs["on_end"])  # push-to-talk: click to stop

    def test_ignored_while_still_thinking(self):
        app = fake_app(speaking=False, busy=True)
        app._on_wake()
        app.recorder.start.assert_not_called()

    def test_stopping_resumes_wake_listener(self):
        app = fake_app(recording=True)
        with mock.patch("jarvis.app.threading.Thread"):
            app.toggle_listen()
        app.recorder.stop.assert_called_once()
        app.wake.resume.assert_called_once()


MODEL = config.WAKEWORD_DIR / "hey_jarvis_v0.1.onnx"
VOICE = config.VOICES_DIR / "en_GB-alan-medium.onnx"


@unittest.skipUnless(MODEL.exists() and VOICE.exists(), "wake word model or Piper voice not downloaded")
class DetectionTests(unittest.TestCase):
    """Real model on synthesized speech: the phrase should score high, other speech low."""

    @classmethod
    def setUpClass(cls):
        from openwakeword.model import Model
        from piper import PiperVoice
        cls.model = Model(inference_framework="onnx", **wakeword.model_paths("hey_jarvis"))
        cls.voice = PiperVoice.load(str(VOICE), config_path=str(VOICE) + ".json")

    def peak(self, text):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            self.voice.synthesize_wav(text, wf)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            a = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32)
        a = np.interp(np.linspace(0, len(a), int(len(a) * RATE / rate), endpoint=False), np.arange(len(a)), a)
        audio = np.concatenate([np.zeros(RATE), a, np.zeros(RATE)]).astype(np.int16)
        self.model.reset()
        return max(max(self.model.predict(audio[i:i + 1280]).values()) for i in range(0, len(audio) - 1280, 1280))

    def test_phrase_detected_other_speech_not(self):
        self.assertGreater(self.peak("Hey Jarvis."), 0.5)
        self.assertLess(self.peak("Remind me to call my sister tomorrow."), 0.5)
