"""Drexya desktop window."""
import math
import os
import queue
import sys
import threading
import webbrowser
from datetime import datetime

import customtkinter as ctk

from . import config, profiles, providers, safety, wakeword
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

CALENDAR_CHOICES = {"Off": "none", "Google Calendar": "google"}  # menu label -> calendar_provider
EMAIL_CHOICES = {"Off": "none", "Gmail": "google"}               # menu label -> email_provider
LOCATION_CHOICES = {                                             # menu label -> location_mode
    "Detect automatically (Windows, then IP address)": "auto",
    "Use my IP address": "ip",
    "Always use my home city (private)": "home",
}

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
    def __init__(self, master, cfg, on_save, first_run=False, tools=None):
        super().__init__(master)
        self.title("Drexya settings")
        self.geometry("440x660")
        self.configure(fg_color=PANEL)
        self.resizable(False, False)
        self.transient(master)
        self.after(100, self.grab_set)
        self.cfg, self.on_save, self.tools = cfg, on_save, tools
        self._edits = {}  # profile id -> (name, city) typed in but not saved yet

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

        if tools is not None and cfg.get("profiles_enabled", True):
            ctk.CTkLabel(body, text="Who's using Drexya (each person has their own notes and reminders)",
                         text_color=TEXT, wraplength=390, justify="left").pack(**pad)
            row = ctk.CTkFrame(body, fg_color=PANEL)
            row.pack(padx=24, anchor="w")
            self.profile_menu = ctk.CTkOptionMenu(row, values=["Main"], width=260, fg_color=CYAN_DIM,
                                                  button_color=CYAN_DIM, button_hover_color=CYAN,
                                                  command=self._pick_profile)
            self.profile_menu.pack(side="left")
            ctk.CTkButton(row, text="+ Add person", width=120, fg_color=CYAN_DIM, hover_color=CYAN,
                          command=self._add_profile).pack(side="left", padx=(8, 0))
        else:
            self.profile_menu = None
        self._profile = tools.profile if tools is not None else profiles.DEFAULT

        ctk.CTkLabel(body, text="What should Drexya call you?", text_color=TEXT).pack(**pad)
        self.name = ctk.CTkEntry(body, width=390, placeholder_text="e.g. Marcus, or 'sir'")
        self.name.pack(padx=24, anchor="w")

        ctk.CTkLabel(body, text="Home city (for weather)", text_color=TEXT).pack(**pad)
        self.city = ctk.CTkEntry(body, width=390, placeholder_text="e.g. Baton Rouge")
        self.city.pack(padx=24, anchor="w")
        self._refresh_profiles()
        self._fill_person(self._profile)

        ctk.CTkLabel(body, text="Location for weather", text_color=TEXT).pack(**pad)
        self.location = ctk.CTkOptionMenu(body, values=list(LOCATION_CHOICES), width=390,
                                          fg_color=CYAN_DIM, button_color=CYAN_DIM, button_hover_color=CYAN)
        self.location.set(next((k for k, v in LOCATION_CHOICES.items()
                                if v == cfg.get("location_mode", "auto")), list(LOCATION_CHOICES)[0]))
        self.location.pack(padx=24, anchor="w")

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

        self.wake_on = ctk.CTkSwitch(body, text="Listen for a wake word (uses more battery)", text_color=TEXT,
                                     progress_color=CYAN)
        if cfg.get("wake_word_enabled"):
            self.wake_on.select()
        self.wake_on.pack(**pad)
        self._wake_choices = {wakeword.phrase(k): k for k in wakeword.PRETRAINED}
        current_wake = cfg.get("wake_word", "hey_jarvis")
        if current_wake not in wakeword.PRETRAINED:  # custom model path from config.json
            self._wake_choices[wakeword.phrase(current_wake)] = current_wake
        self.wake_word = ctk.CTkOptionMenu(body, values=list(self._wake_choices), width=180,
                                           fg_color=CYAN_DIM, button_color=CYAN_DIM, button_hover_color=CYAN)
        self.wake_word.set(wakeword.phrase(current_wake))
        self.wake_word.pack(padx=24, anchor="w")
        ctk.CTkLabel(body, text="Say it, then just talk. Say it again to interrupt.",
                     text_color=MUTED).pack(padx=24, anchor="w")

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

        ctk.CTkLabel(body, text="Calendar", text_color=TEXT).pack(**pad)
        self.calendar = ctk.CTkOptionMenu(body, values=list(CALENDAR_CHOICES), width=180,
                                          fg_color=CYAN_DIM, button_color=CYAN_DIM, button_hover_color=CYAN)
        self.calendar.set(next((k for k, v in CALENDAR_CHOICES.items()
                                if v == cfg.get("calendar_provider", "none")), "Off"))
        self.calendar.pack(padx=24, anchor="w")

        ctk.CTkLabel(body, text="Email", text_color=TEXT).pack(**pad)
        self.email = ctk.CTkOptionMenu(body, values=list(EMAIL_CHOICES), width=180,
                                       fg_color=CYAN_DIM, button_color=CYAN_DIM, button_hover_color=CYAN)
        self.email.set(next((k for k, v in EMAIL_CHOICES.items()
                             if v == cfg.get("email_provider", "none")), "Off"))
        self.email.pack(padx=24, anchor="w")
        ctk.CTkLabel(body, text="Drexya always reads an email back and asks before sending it.",
                     text_color=MUTED).pack(padx=24, anchor="w")

        google_row = ctk.CTkFrame(body, fg_color=PANEL)
        google_row.pack(padx=24, pady=(6, 0), anchor="w")
        ctk.CTkButton(google_row, text="Connect Google", width=130, fg_color=CYAN_DIM, hover_color=CYAN,
                      command=self._connect_google).pack(side="left")
        self.google_status = ctk.CTkLabel(
            google_row, text_color=MUTED,
            text="  Connected" if config.GOOGLE_TOKEN_PATH.exists() else "  Not connected")
        self.google_status.pack(side="left")

        ctk.CTkLabel(body, text="Home Assistant address (optional)", text_color=TEXT).pack(**pad)
        self.ha_url = ctk.CTkEntry(body, width=390, placeholder_text="http://homeassistant.local:8123")
        self.ha_url.insert(0, cfg.get("ha_url", ""))
        self.ha_url.pack(padx=24, anchor="w")
        ctk.CTkLabel(body, text="Home Assistant access token", text_color=TEXT).pack(**pad)
        self.ha_token = ctk.CTkEntry(body, width=390, show="•", placeholder_text="Profile → Security → Long-lived tokens")
        self.ha_token.insert(0, cfg.get("ha_token", ""))
        self.ha_token.pack(padx=24, anchor="w")

        ctk.CTkButton(self, text="Save", fg_color=CYAN, text_color=BG, hover_color="#7fe6ff",
                      command=self._save, width=390).pack(padx=24, pady=16, anchor="w")

    def _show_model_note(self, label):
        mid = self._model_ids[label]
        self.model_note.configure(text=config.MODELS[mid][1],
                                  text_color="#ffb347" if mid == "claude-fable-5-1" else MUTED)

    def _chosen_providers(self) -> dict:
        return {"calendar_provider": CALENDAR_CHOICES[self.calendar.get()],
                "email_provider": EMAIL_CHOICES[self.email.get()]}

    def _connect_google(self):
        features = providers.google_features(self._chosen_providers())
        if not features:
            self.google_status.configure(text="  Choose Google above first")
            return
        self.google_status.configure(text="  Waiting for you in the browser…")

        def run():
            try:
                from .providers import google
                msg = google.connect(features)
            except Exception as e:
                msg = f"Couldn't connect: {e}"
            self.after(0, lambda: self.google_status.configure(text=f"  {msg}"))

        threading.Thread(target=run, daemon=True).start()

    # ---------- profiles ----------
    def _people(self) -> list:
        if self.tools is None:
            return [{"id": profiles.DEFAULT, "name": self.cfg.get("user_name") or "Main",
                     "home_city": self.cfg.get("home_city", "")}]
        return profiles.all_profiles(self.tools.store, self.cfg)

    def _refresh_profiles(self):
        if self.profile_menu is None:
            return
        self._profile_labels = {p["name"]: p["id"] for p in self._people()}
        self.profile_menu.configure(values=list(self._profile_labels))
        self.profile_menu.set(next(n for n, pid in self._profile_labels.items() if pid == self._profile))

    def _fill_person(self, pid):
        """Show a profile's name and city, including unsaved edits."""
        person = next((p for p in self._people() if p["id"] == pid), self._people()[0])
        name, city = self._edits.get(pid, (person["name"] if pid != profiles.DEFAULT else
                                           self.cfg.get("user_name", ""), person["home_city"]))
        for entry, value in ((self.name, name), (self.city, city)):
            entry.delete(0, "end")
            entry.insert(0, value)

    def _pick_profile(self, label):
        self._edits[self._profile] = (self.name.get().strip(), self.city.get().strip())
        self._profile = self._profile_labels[label]
        self._fill_person(self._profile)

    def _add_profile(self):
        name = ctk.CTkInputDialog(text="Their name:", title="Add a person").get_input()
        name = " ".join((name or "").split())
        if not name or profiles.find(self.tools.store, self.cfg, name):
            return
        self.tools.store.run("INSERT INTO profiles (id, name, home_city, created) VALUES (?, ?, '', ?)",
                             (profiles.profile_id(name), name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self._edits[self._profile] = (self.name.get().strip(), self.city.get().strip())
        self._profile = profiles.profile_id(name)
        self._refresh_profiles()
        self._fill_person(self._profile)

    def _save_people(self):
        self._edits[self._profile] = (self.name.get().strip(), self.city.get().strip())
        for pid, (name, city) in self._edits.items():
            if pid == profiles.DEFAULT:
                self.cfg.update({"user_name": name, "home_city": city})
            elif self.tools is not None:
                self.tools.store.run("UPDATE profiles SET name = COALESCE(NULLIF(?, ''), name), home_city = ? "
                                     "WHERE id = ?", (name, city, pid))
        if self.tools is not None and self._profile != self.tools.profile:
            self.tools.switch_profile(self._profile)

    def _save(self):
        self._save_people()
        self.cfg.update({
            **self._chosen_providers(),
            "api_key": self.key.get().strip(),
            "model": self._model_ids[self.model.get()],
            "location_mode": LOCATION_CHOICES[self.location.get()],
            "ha_url": self.ha_url.get().strip(),
            "ha_token": self.ha_token.get().strip(),
            "whisper_model": self.whisper.get(),
            "voice_enabled": bool(self.voice.get()),
            "web_search": bool(self.search.get()),
            "memory_enabled": bool(self.memory.get()),
            "wake_word_enabled": bool(self.wake_on.get()),
            "wake_word": self._wake_choices[self.wake_word.get()],
        })
        config.save(self.cfg)
        self.on_save()
        self.destroy()


class ConfirmDialog(ctk.CTkToplevel):
    """Yes/No box for an irreversible action. on_answer(bool) is called once."""

    def __init__(self, master, question, detail, on_answer):
        super().__init__(master)
        self.title("Drexya: please confirm")
        self.geometry("440x360")
        self.configure(fg_color=PANEL)
        self.transient(master)
        self.attributes("-topmost", True)
        self.on_answer = on_answer
        ctk.CTkLabel(self, text=question, text_color=AMBER, wraplength=400, justify="left",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(padx=20, pady=(18, 8), anchor="w")
        box = ctk.CTkTextbox(self, fg_color=BG, text_color=TEXT, wrap="word", height=200)
        box.insert("1.0", detail)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=20)
        row = ctk.CTkFrame(self, fg_color=PANEL)
        row.pack(pady=14)
        ctk.CTkButton(row, text="Yes", width=120, fg_color=CYAN, text_color=BG, hover_color="#7fe6ff",
                      command=lambda: self.answer(True)).pack(side="left", padx=8)
        ctk.CTkButton(row, text="No", width=120, fg_color=CYAN_DIM, hover_color=RED,
                      command=lambda: self.answer(False)).pack(side="left", padx=8)
        self.bind("<Escape>", lambda e: self.answer(False))
        self.protocol("WM_DELETE_WINDOW", lambda: self.answer(False))
        self.after(50, self.focus_force)

    def answer(self, ok):
        if self.on_answer:
            self.on_answer(ok)
            self.on_answer = None
        self.destroy()


class JarvisApp(ctk.CTk):
    CONFIRM_TIMEOUT = 60  # seconds to answer a confirmation before it counts as no

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
        self.speaking = False  # True while a reply is being spoken, so it can be interrupted
        self.wake = None       # WakeListener when the wake word is on
        self.confirming = False  # a confirmation is open; mic/wake word belong to it
        self._voice_turn = False  # the current request was spoken, so confirm by voice too
        self.tools = Tools(on_timer_done=self._timer_done, cfg=self.cfg, on_reminder=self._reminder_due,
                           confirm=self._confirm, on_profile_switch=lambda pid: config.save(self.cfg))
        self.brain = None
        self.recorder = Recorder()
        self.transcriber = Transcriber(self.cfg["whisper_model"])
        self.speaker = Speaker(self.cfg["piper_voice"])

        self._build_ui()
        self._init_brain()
        self._register_hotkey()
        self._setup_wake()

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
        if state == "idle" and not detail and self.wake and not self.wake.error:
            text = f"Online — say “{wakeword.phrase(self.cfg['wake_word'])}” or click the core"
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

    def _setup_wake(self):
        """(Re)start the wake word listener to match settings."""
        if self.wake:
            self.wake.stop()
            self.wake = None
        if self.cfg.get("wake_word_enabled"):
            self.wake = wakeword.WakeListener(self.cfg.get("wake_word", "hey_jarvis"),
                                              float(self.cfg.get("wake_word_threshold", 0.5)),
                                              on_wake=lambda: self.ui(self._on_wake)).start()

    def open_settings(self, first_run=False):
        SettingsDialog(self, self.cfg, on_save=self._settings_saved, first_run=first_run, tools=self.tools)

    def _settings_saved(self):
        self._init_brain()
        self._setup_wake()
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
        name = self.tools.effective_cfg().get("user_name") or "sir"
        line = f"Good {part}, {name}. All systems online."
        self._append("jarvis", line)
        self._speak_async(line)

    # ---------- interaction ----------
    def toggle_listen(self, hands_free=False):
        """Click, hotkey or wake word. Stops recording if recording; otherwise starts it,
        cutting off Drexya mid-sentence if he's talking. hands_free stops on silence."""
        if self.confirming:
            return  # the confirmation is using the mic; answer it first
        if self.recorder.recording:
            audio = self.recorder.stop()
            if self.wake:
                self.wake.resume()
            self._set_state("thinking", "Transcribing…")
            threading.Thread(target=self._transcribe_then_ask, args=(audio,), daemon=True).start()
            return
        if self.speaking:
            self.speaker.stop()  # interrupt; the reply thread finishes on its own
        elif self.busy:
            return  # still thinking about the last request
        try:
            on_end = (lambda: self.ui(self._heard_enough)) if hands_free else None
            self.recorder.start(on_end=on_end)
            if self.wake:
                self.wake.pause()
            self._set_state("listening", "Listening…" if hands_free else None)
        except Exception as e:
            self._append("jarvis", f"I can't access the microphone: {e}")

    def _on_wake(self):
        if not self.recorder.recording:
            self.toggle_listen(hands_free=True)

    def _heard_enough(self):
        if self.recorder.recording:
            self.toggle_listen()

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
        self._voice_turn = speak
        reply = self.brain.ask(
            text, on_tool=lambda name: self.ui(self._set_state, "thinking",
                                               f"Using {name.replace('_', ' ')}…"))
        self.ui(self._append, "jarvis", reply)
        if speak and self.cfg.get("voice_enabled", True):
            self.ui(self._set_state, "speaking")
            self._say(reply)  # whole reply as one clip, no gaps between sentences
        self.busy = False
        self.ui(self._idle_unless_listening)

    def _idle_unless_listening(self):
        if not self.recorder.recording:  # the user may have interrupted to ask something else
            self._set_state("idle")

    def _say(self, text):
        """Speak (blocking) and mark it interruptible."""
        self.speaking = True
        try:
            self.speaker.say(text)
        finally:
            self.speaking = False

    def _speak_async(self, text):
        if self.cfg.get("voice_enabled", True):
            threading.Thread(target=self._say, args=(text,), daemon=True).start()

    # ---------- confirmations ----------
    def _confirm(self, question, detail) -> bool:
        """Ask before an irreversible action. Runs on the worker thread and blocks until the
        user clicks Yes/No or, for spoken requests, says yes or no. Silence, an unclear answer
        or a minute with no answer all mean no."""
        answers = queue.Queue()
        heard = threading.Event()  # set when answered, so a voice listen can stop early
        self.confirming = True

        def answer(ok):
            heard.set()
            answers.put(ok)

        self.ui(self._show_confirm, question, detail, answer)
        if self._voice_turn and self.cfg.get("voice_enabled", True):
            self.ui(self._set_state, "speaking", "Waiting for your yes or no…")
            self._say(f"{question} Say yes or no.")
            if not heard.is_set():
                threading.Thread(target=self._listen_yes_no, args=(answer, heard), daemon=True).start()
        else:
            self.ui(self._set_state, "thinking", "Waiting for you to confirm…")
        try:
            ok = answers.get(timeout=self.CONFIRM_TIMEOUT)
        except queue.Empty:
            ok = False
        self.confirming = False
        self.ui(self._close_confirm)
        self.ui(self._set_state, "thinking")
        return ok

    def _show_confirm(self, question, detail, answer):
        self._confirm_dialog = ConfirmDialog(self, question, detail, answer)

    def _close_confirm(self):
        dialog = getattr(self, "_confirm_dialog", None)
        if dialog is not None and dialog.winfo_exists():
            dialog.on_answer = None
            dialog.destroy()
        self._confirm_dialog = None

    def _listen_yes_no(self, answer, heard):
        """Record one short hands-free reply and turn it into yes/no. Unclear: leave it to the dialog."""
        ended = threading.Event()
        try:
            if self.wake:
                self.wake.pause()
            self.recorder.start(on_end=ended.set)
            self.ui(self._set_state, "listening", "Say yes or no…")
            while not (ended.wait(0.1) or heard.is_set()):
                pass
            audio = self.recorder.stop()
            if heard.is_set():
                return
            reply = safety.parse_yes_no(self.transcriber.transcribe(audio))
            if reply is not None:
                answer(reply)
            else:
                self.ui(self._set_state, "thinking", "Didn't catch that. Use the buttons.")
        except Exception as e:
            print(f"[confirm] voice answer failed: {e}")
        finally:
            if self.recorder.recording:
                self.recorder.stop()
            if self.wake:
                self.wake.resume()

    def _timer_done(self, label):
        name = self.tools.effective_cfg().get("user_name") or "sir"
        self._announce(f"{name}, your {label} timer is done.")

    def _reminder_due(self, text, late, profile=profiles.DEFAULT):
        # Say whose reminder it is: on a shared computer it may not be the active person's
        person = next((p for p in profiles.all_profiles(self.tools.store, self.cfg) if p["id"] == profile), None)
        name = (person["name"] if person and person["name"] != "Main" else None) or "sir"
        self._announce(f"While I was off, {name} had a reminder: {text}." if late
                       else f"{name}, a reminder: {text}.")

    def _announce(self, line):
        """Speak and show something Drexya says unprompted (timers, reminders). Any thread."""
        self.ui(self._append, "jarvis", line)
        self.ui(self.bell)
        self.ui(self.deiconify)
        self.ui(self.lift)
        self._speak_async(line)


def main():
    JarvisApp().mainloop()
