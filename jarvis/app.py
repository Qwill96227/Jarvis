"""Drexya desktop window."""
import math
import os
import sys
import threading
import webbrowser
from datetime import datetime

import customtkinter as ctk

from . import config
from .brain import Brain
from .tools import Tools, keyboard
from .voice import Recorder, Speaker, Transcriber

BG = "#070b14"
PANEL = "#0d1424"
CYAN = "#29d4ff"
CYAN_DIM = "#0f4a5c"
AMBER = "#ffb347"
RED = "#ff4d5e"
TEXT = "#d8e6f3"
MUTED = "#6b7f96"

STATE_COLORS = {"idle": CYAN, "listening": RED, "thinking": AMBER, "speaking": CYAN}
STATE_TEXT = {
    "idle": "Online — click the core or press {hk}",
    "listening": "Listening… click again when you're done",
    "thinking": "Thinking…",
    "speaking": "Speaking",
}


def resource(path):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, path)


class Reactor(ctk.CTkCanvas):
    """The glowing arc-reactor button. Pulses/spins depending on state."""

    SIZE = 190

    def __init__(self, master, on_click):
        super().__init__(master, width=self.SIZE, height=self.SIZE, bg=BG,
                         highlightthickness=0, cursor="hand2")
        self.state = "idle"
        self.t = 0.0
        self.bind("<Button-1>", lambda e: on_click())
        self._tick()

    def set_state(self, state):
        self.state = state

    def _tick(self):
        self.delete("all")
        c = self.SIZE / 2
        color = STATE_COLORS[self.state]
        self.t += 0.06
        pulse = (math.sin(self.t * (3 if self.state == "listening" else 1.5)) + 1) / 2

        # outer glow rings
        for i, r in enumerate((88, 80, 72)):
            w = 1 + (pulse * 2 if i == 0 else 0)
            self.create_oval(c - r, c - r, c + r, c + r, outline=CYAN_DIM if i else color, width=w)

        # rotating segments
        spin = self.t * (4 if self.state == "thinking" else 0.6)
        for k in range(10):
            start = math.degrees(spin) + k * 36
            self.create_arc(c - 62, c - 62, c + 62, c + 62, start=start, extent=22,
                            style="arc", outline=color, width=6)

        # core
        core = 30 + pulse * (8 if self.state in ("listening", "speaking") else 3)
        self.create_oval(c - core - 8, c - core - 8, c + core + 8, c + core + 8,
                         outline=color, width=2)
        self.create_oval(c - core, c - core, c + core, c + core, fill=color, outline="")
        self.create_oval(c - core * 0.45, c - core * 0.45, c + core * 0.45, c + core * 0.45,
                         fill="#ffffff", outline="")
        self.after(33, self._tick)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, cfg, on_save, first_run=False):
        super().__init__(master)
        self.title("Drexya settings")
        self.geometry("440x660")
        self.configure(fg_color=PANEL)
        self.resizable(False, False)
        self.transient(master)
        self.after(100, self.grab_set)
        self.cfg, self.on_save = cfg, on_save

        # Scrollable so new settings fit; Save stays pinned at the bottom
        body = ctk.CTkScrollableFrame(self, fg_color=PANEL)
        body.pack(fill="both", expand=True)
        pad = {"padx": 24, "pady": (10, 0), "anchor": "w"}
        if first_run:
            ctk.CTkLabel(body, text="Welcome. Let's get you set up.", text_color=CYAN,
                         font=ctk.CTkFont(size=18, weight="bold")).pack(**pad)

        ctk.CTkLabel(body, text="Claude API key", text_color=TEXT).pack(**pad)
        self.key = ctk.CTkEntry(body, width=390, show="•", placeholder_text="sk-ant-...")
        self.key.insert(0, cfg.get("api_key", ""))
        self.key.pack(padx=24, anchor="w")
        link = ctk.CTkLabel(body, text="How to get a key (opens your browser)",
                            text_color=MUTED, cursor="hand2")
        link.pack(padx=24, anchor="w")
        link.bind("<Button-1>", lambda e: webbrowser.open("https://platform.claude.com/docs/en/get-api-key"))

        ctk.CTkLabel(body, text="Brain (Claude model)", text_color=TEXT).pack(**pad)
        self._model_ids = {label: mid for mid, (label, _) in config.MODELS.items()}
        current = config.MODELS.get(cfg.get("model"), config.MODELS["claude-haiku-5-5"])
        self.model = ctk.CTkOptionMenu(body, values=list(self._model_ids), width=390,
                                       fg_color=CYAN_DIM, button_color=CYAN_DIM,
                                       button_hover_color=CYAN, command=self._show_model_note)
        self.model.set(current[0])
        self.model.pack(padx=24, anchor="w")
        self.model_note = ctk.CTkLabel(body, text="", text_color=MUTED, wraplength=390, justify="left")
        self.model_note.pack(padx=24, anchor="w")
        self._show_model_note(current[0])

        ctk.CTkLabel(body, text="What should Drexya call you?", text_color=TEXT).pack(**pad)
        self.name = ctk.CTkEntry(body, width=390, placeholder_text="e.g. Marcus, or 'sir'")
        self.name.insert(0, cfg.get("user_name", ""))
        self.name.pack(padx=24, anchor="w")

        ctk.CTkLabel(body, text="Home city (for weather)", text_color=TEXT).pack(**pad)
        self.city = ctk.CTkEntry(body, width=390, placeholder_text="e.g. Baton Rouge")
        self.city.insert(0, cfg.get("home_city", ""))
        self.city.pack(padx=24, anchor="w")

        ctk.CTkLabel(body, text="Speech recognition model (restart to apply)",
                     text_color=TEXT).pack(**pad)
        self.whisper = ctk.CTkOptionMenu(body, values=["tiny.en", "base.en", "small.en"], width=180,
                                         fg_color=CYAN_DIM, button_color=CYAN_DIM,
                                         button_hover_color=CYAN)
        self.whisper.set(cfg.get("whisper_model", "base.en"))
        self.whisper.pack(padx=24, anchor="w")
        ctk.CTkLabel(body, text="tiny = fastest · base = balanced · small = most accurate",
                     text_color=MUTED).pack(padx=24, anchor="w")

        self.voice = ctk.CTkSwitch(body, text="Speak replies out loud", text_color=TEXT,
                                   progress_color=CYAN)
        if cfg.get("voice_enabled", True):
            self.voice.select()
        self.voice.pack(**pad)

        self.search = ctk.CTkSwitch(body, text="Allow web search (~1¢ per search)", text_color=TEXT,
                                    progress_color=CYAN)
        if cfg.get("web_search", True):
            self.search.select()
        self.search.pack(**pad)

        self.memory = ctk.CTkSwitch(body, text="Remember things about me between chats", text_color=TEXT,
                                    progress_color=CYAN)
        if cfg.get("memory_enabled", True):
            self.memory.select()
        self.memory.pack(**pad)

        ctk.CTkButton(self, text="Save", fg_color=CYAN, text_color=BG, hover_color="#7fe6ff",
                      command=self._save, width=390).pack(padx=24, pady=16, anchor="w")

    def _show_model_note(self, label):
        mid = self._model_ids[label]
        self.model_note.configure(text=config.MODELS[mid][1],
                                  text_color="#ffb347" if mid == "claude-fable-5-1" else MUTED)

    def _save(self):
        self.cfg.update({
            "api_key": self.key.get().strip(),
            "model": self._model_ids[self.model.get()],
            "user_name": self.name.get().strip(),
            "home_city": self.city.get().strip(),
            "whisper_model": self.whisper.get(),
            "voice_enabled": bool(self.voice.get()),
            "web_search": bool(self.search.get()),
            "memory_enabled": bool(self.memory.get()),
        })
        config.save(self.cfg)
        self.on_save()
        self.destroy()


class JarvisApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.cfg = config.load()
        self.title("Drexya")
        self.geometry("460x720")
        self.minsize(400, 600)
        self.configure(fg_color=BG)
        try:
            self.iconbitmap(resource("assets/jarvis.ico"))
        except Exception:
            pass

        self.busy = False
        self.tools = Tools(on_timer_done=self._timer_done, cfg=self.cfg)
        self.brain = None
        self.recorder = Recorder()
        self.transcriber = Transcriber(self.cfg["whisper_model"])
        self.speaker = Speaker(self.cfg["piper_voice"])

        self._build_ui()
        self._init_brain()
        self._register_hotkey()

        if not self.cfg.get("api_key"):
            self.after(400, lambda: self.open_settings(first_run=True))
        else:
            self.after(800, self._greet)

    # ---------- UI ----------
    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color=BG)
        top.pack(fill="x", padx=18, pady=(16, 0))
        ctk.CTkLabel(top, text="DREXYA", text_color=CYAN,
                     font=ctk.CTkFont(family="Consolas", size=24, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="⚙", width=36, fg_color=PANEL, hover_color=CYAN_DIM,
                      command=self.open_settings).pack(side="right")
        ctk.CTkButton(top, text="New chat", width=80, fg_color=PANEL, hover_color=CYAN_DIM,
                      command=self._new_chat).pack(side="right", padx=6)

        self.reactor = Reactor(self, on_click=self.toggle_listen)
        self.reactor.pack(pady=(14, 4))
        self.status = ctk.CTkLabel(self, text="", text_color=MUTED)
        self.status.pack()

        self.log = ctk.CTkTextbox(self, fg_color=PANEL, text_color=TEXT, wrap="word",
                                  font=ctk.CTkFont(size=14), corner_radius=12)
        self.log.pack(fill="both", expand=True, padx=18, pady=12)
        self.log.tag_config("you", foreground=MUTED)
        self.log.tag_config("jarvis", foreground=TEXT)
        self.log.tag_config("label_j", foreground=CYAN)
        self.log.configure(state="disabled")

        bottom = ctk.CTkFrame(self, fg_color=BG)
        bottom.pack(fill="x", padx=18, pady=(0, 16))
        self.entry = ctk.CTkEntry(bottom, placeholder_text="Type a message…", height=40,
                                  fg_color=PANEL, border_color=CYAN_DIM)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self._send_typed())
        ctk.CTkButton(bottom, text="➤", width=44, height=40, fg_color=CYAN, text_color=BG,
                      hover_color="#7fe6ff", command=self._send_typed).pack(side="left", padx=(6, 0))
        ctk.CTkButton(bottom, text="■", width=44, height=40, fg_color=PANEL, hover_color=CYAN_DIM,
                      command=self.speaker.stop).pack(side="left", padx=(6, 0))

        self._set_state("idle")

    def _set_state(self, state, detail=None):
        self.reactor.set_state(state)
        text = detail or STATE_TEXT[state].format(hk=self.cfg.get("hotkey", "").upper())
        self.status.configure(text=text)

    def _append(self, who, text):
        self.log.configure(state="normal")
        if who == "you":
            self.log.insert("end", f"You: {text}\n\n", "you")
        else:
            self.log.insert("end", "Drexya: ", "label_j")
            self.log.insert("end", f"{text}\n\n", "jarvis")
        self.log.configure(state="disabled")
        self.log.see("end")

    def ui(self, fn, *args):
        """Run fn on the UI thread."""
        self.after(0, lambda: fn(*args))

    # ---------- setup ----------
    def _init_brain(self):
        self.brain = Brain(self.cfg, self.tools) if self.cfg.get("api_key") else None

    def _register_hotkey(self):
        if keyboard is None or not self.cfg.get("hotkey"):
            return
        try:
            keyboard.add_hotkey(self.cfg["hotkey"], lambda: self.ui(self.toggle_listen))
        except Exception as e:
            print(f"[hotkey] couldn't register: {e}")

    def open_settings(self, first_run=False):
        SettingsDialog(self, self.cfg, on_save=self._settings_saved, first_run=first_run)

    def _settings_saved(self):
        self._init_brain()
        self._set_state("idle")
        self._greet()

    def _new_chat(self):
        if self.brain:
            self.brain.reset()
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _greet(self):
        hour = datetime.now().hour
        part = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
        name = self.cfg.get("user_name") or "sir"
        line = f"Good {part}, {name}. All systems online."
        self._append("jarvis", line)
        self._speak_async(line)

    # ---------- interaction ----------
    def toggle_listen(self):
        if self.recorder.recording:
            audio = self.recorder.stop()
            self._set_state("thinking", "Transcribing…")
            threading.Thread(target=self._transcribe_then_ask, args=(audio,), daemon=True).start()
            return
        if self.busy:
            return
        self.speaker.stop()
        try:
            self.recorder.start()
            self._set_state("listening")
        except Exception as e:
            self._append("jarvis", f"I can't access the microphone: {e}")

    def _transcribe_then_ask(self, audio):
        if not self.transcriber.ready and self.transcriber.error is None:
            self.ui(self._set_state, "thinking", "Loading speech model (first run only)…")
        try:
            text = self.transcriber.transcribe(audio)
        except Exception as e:
            self.ui(self._append, "jarvis", str(e))
            self.ui(self._set_state, "idle")
            return
        if not text:
            self.ui(self._set_state, "idle", "Didn't catch that — try again")
            return
        self.ui(self._handle, text)

    def _send_typed(self):
        text = self.entry.get().strip()
        if text and not self.busy:
            self.entry.delete(0, "end")
            self._handle(text, speak=False)

    def _handle(self, text, speak=True):
        if self.brain is None:
            self._append("jarvis", "I need an API key first. Click the gear icon.")
            self._set_state("idle")
            return
        self.busy = True
        self._append("you", text)
        self._set_state("thinking")
        threading.Thread(target=self._ask, args=(text, speak), daemon=True).start()

    def _ask(self, text, speak):
        reply = self.brain.ask(
            text, on_tool=lambda name: self.ui(self._set_state, "thinking",
                                               f"Using {name.replace('_', ' ')}…"))
        self.ui(self._append, "jarvis", reply)
        if speak and self.cfg.get("voice_enabled", True):
            self.ui(self._set_state, "speaking")
            self.speaker.say(reply)  # whole reply as one clip, no gaps between sentences
        self.busy = False
        self.ui(self._set_state, "idle")

    def _speak_async(self, text):
        if self.cfg.get("voice_enabled", True):
            threading.Thread(target=self.speaker.say, args=(text,), daemon=True).start()

    def _timer_done(self, label):
        name = self.cfg.get("user_name") or "sir"
        line = f"{name}, your {label} timer is done."
        self.ui(self._append, "jarvis", line)
        self.ui(self.bell)
        self.ui(self.deiconify)
        self.ui(self.lift)
        self._speak_async(line)


def main():
    JarvisApp().mainloop()
