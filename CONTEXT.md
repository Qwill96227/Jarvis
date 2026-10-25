# Jarvis: project context

Read this first. It explains what this project is, how it's built, where things stand, and what to do next.

## What this is

> **Renamed to Drexya (2026-10-17).** Everything user-facing says Drexya: window, persona, transcript, `Drexya.exe`, `DrexyaSetup.exe`, `Drexya-Windows.zip`, shortcuts. Deliberately kept: the `jarvis/` package, `run_jarvis.py`, `assets/jarvis.ico`, the repo/folder name, and the data folder `%APPDATA%\Jarvis` (renaming it would lose existing API keys, settings and the downloaded voice).

A J.A.R.V.I.S.-style voice assistant packaged as a **downloadable Windows desktop app**, built by Quincy as a gift for his roommate.

- **Target machine:** the roommate's regular Windows laptop. No GPU, so no local LLMs.
- **Distribution:** a `.exe` built with PyInstaller: `Output\DrexyaSetup.exe` (Inno Setup) or `Drexya-Windows.zip`.
- **Repo:** `github.com/Qwill96227/Jarvis` (private, branch `main`)
- **Local working copy:** `C:\Users\Quincy\AI Projects\Jarvis`. The old copy at `E:\Projects\jarvis` is obsolete and can be deleted.

## How it works

```
🎤 mic (push-to-talk or wake word) → Whisper (local) → text → Claude API + tools → reply → Piper TTS (local) → 🔊
```

- **Brain:** Claude API. Model picker in settings (`config.MODELS`, Haiku 5.5 default). Each user supplies their own API key in settings, stored in `%APPDATA%\Jarvis\config.json`, **never** bundled or committed.
- **Speech-to-text:** `faster-whisper` (`base.en` default) on CPU int8.
- **Text-to-speech:** `piper-tts` voice `en_GB-alan-medium`, whole reply played as one clip; Windows SAPI fallback.
- **Trigger:** click the core or `Ctrl+Alt+J` (push-to-talk), or the optional wake word (off by default; "Hey Jarvis"), which records hands-free until silence. Any of them interrupts speech.
- **Typed messages** get text-only replies. **Voice messages** get spoken replies.

## Code map

The batch scripts live in `script fixes\` and `cd` to the repo root (`%~dp0..`) before running.

| File | Purpose |
|---|---|
| `run_jarvis.py` | Entry point. Redirects stdout/stderr to a log when windowed; on crash shows a MessageBox and writes `crash.log` |
| `jarvis/app.py` | customtkinter window, settings (scrollable), confirmation dialog (+PIN), activity log viewer, wake word/interruption, threading |
| `jarvis/brain.py` | Claude tool-use loop: multi-step (max_tool_steps), is_error results, partial-progress replies on failure, resets history when the profile changes |
| `jarvis/tools.py` | Core tools + `Tools` class, which inherits each feature's mixin. `schemas()` picks tool groups from settings; `run()` is the gate: confirmation/PIN, retries, audit log |
| `jarvis/storage.py` | SQLite `%APPDATA%\Jarvis\drexya.db`: memories, reminders, notes, profiles, audit |
| `jarvis/memory.py` | remember / recall / forget; recent memories go in the system prompt |
| `jarvis/reminders.py` | Date/time reminders + background scheduler (survive restarts; missed ones announced) |
| `jarvis/calendar_tools.py`, `email_tools.py` | Calendar and Gmail tools, provider-agnostic |
| `jarvis/providers/` | `base.py` interfaces, `google.py` (OAuth, Google Calendar, Gmail). Add Outlook here |
| `jarvis/system_tools.py` | Close apps, windows, screenshots, file search/open/move (inside user profile only), brightness, Wi-Fi |
| `jarvis/location.py` | Windows location → IP → home city, cached 10 min; weather uses it when no place is named |
| `jarvis/home_assistant.py` | Lights, switches, fans, thermostats via HA REST (locks/garage/alarms excluded on purpose) |
| `jarvis/wakeword.py` | openWakeWord listener + `EndOfSpeech` silence detection |
| `jarvis/safety.py` | Which tools need confirmation/PIN, yes/no parsing, PIN hashing (PBKDF2), audit log |
| `jarvis/profiles.py` | People sharing the laptop: list/switch/create; per-profile notes, memories, reminders |
| `jarvis/voice.py` | `Recorder` (optional hands-free stop), `Transcriber`, `Speaker` |
| `jarvis/config.py` | Settings defaults and paths in `%APPDATA%\Jarvis` |
| `tests/` | unittest suite (135 tests): `.\.venv\Scripts\python -m unittest discover -s tests -t .` |
| `script fixes\run.bat` / `build.bat` | Run from source / build `dist\Drexya\Drexya.exe` + installer or zip |

### Adding a tool
Add a schema to `TOOL_SCHEMAS` (or a feature module's `SCHEMAS`) and a `t_<tool_name>` method on `Tools` (or that module's mixin). Register a new module's group in `Tools.schemas()`. If it's irreversible, add it to `safety.DEFAULT_CONFIRM_TOOLS`; if sensitive, `DEFAULT_PIN_TOOLS`; if it changes something, add a phrase to `brain.DID`.

### Important implementation details
- Web search tool `web_search_20250305`, toggled in settings.
- Assistant content is appended to history **exactly as returned**; `pause_turn` continuations merge into the previous assistant message.
- History trimming only cuts at a plain-text user message. On an API error with no tools run, `_rollback()`; if tools already ran, history is kept so they aren't repeated.
- The confirmation gate is in `Tools.run`, not the prompt: only an explicit `True` from `confirm()` proceeds (`is not True`, since `1 == True`).
- Tool results from email/web are untrusted; the system prompt says never to follow instructions in them (verified against a planted forwarding instruction).
- All Claude, Whisper, Piper and wake word work runs off the UI thread; UI updates go through `self.ui(fn, ...)`.

## Current status (2026-10-25)

- ✅ Runs from source and as an exe (DLL fix: `build.bat` copies current `msvcp140`/`vcruntime140*` from System32).
- ✅ Features added 2026-10-25, each committed with tests and live-tested with Claude: persistent memory, reminders, Google Calendar, Gmail, system control, location, Home Assistant, wake word + interruption, multi-step with enforced confirmations, profiles, PIN + audit log.
- ⚠️ **Defender quarantined `Drexya.exe`** (2026-10-18, `Trojan:Win32/Bearfoos.B!ml`, a common PyInstaller false positive). Desktop shortcut now runs from source via `.venv\Scripts\pythonw.exe run_jarvis.py`. Fix: submit `Drexya-Windows.zip` to microsoft.com/wdsi/filesubmission as a false positive; long term, code signing.
- ⚠️ **Needs Quincy's accounts to test for real:** Google (create OAuth client, see README), Home Assistant URL/token. Both are tested against mocks only.
- ⚠️ On Quincy's PC, Windows location access is denied and IP geolocation says Seattle (home is Baton Rouge), so auto location gives the wrong city until Windows location is allowed or "Always use my home city" is chosen.
- ⏳ Exe not rebuilt since these features: new deps (Google libs, Pillow, openwakeword) need a rebuild + Defender check.
- 💡 Voice quality: ElevenLabs was researched (Quincy's choice); waiting on his API key. The `alan-medium` Piper model is the main source of the rough sound.
- Not included on purpose: voice identification for profiles (too heavy/unreliable), Wi-Fi radio off (needs admin), file delete, lock/garage control.

## Next steps (in order)

1. Run `script fixes\run.bat` and try the new features by voice on real hardware.
2. Set up Google OAuth and Home Assistant if wanted (README).
3. ElevenLabs voice once Quincy has a key.
4. Rebuild the exe; submit to Microsoft as a false positive; consider code signing.
5. Install Inno Setup 6 and build `Output\DrexyaSetup.exe` for the roommate.

## Gotchas

- **`.venv` is git-ignored on purpose** (over 1 GB, machine-specific). `run.bat` creates it.
- **PowerShell** needs `.\` before local paths. **Commit messages:** Windows PowerShell 5.1 mangles quotes when passing `-m` to git; write the message to a file and use `git commit -F`.
- **Tests must never touch real user files.** `tests/helpers.py` redirects `NOTES_PATH` and the Google token/client paths; an early version emptied the real `notes.json`. Any new file under `%APPDATA%\Jarvis` that tools write must be redirected there too.
- **`--windowed` exes have no console**; `run_jarvis.py` redirects stdout/stderr to a log.
- **Python 3.12 (64-bit)** is the target (`build.bat` tries `py -3.12` first).
- **Unsigned exe:** SmartScreen warning (More info → Run anyway) and possible Defender false positives.
- **Mic permission:** Settings → Privacy & security → Microphone → allow desktop apps.
- **Never commit** `config.json`, API keys, `google_client.json` or `google_token.json` (all git-ignored).

## Working style for this project

- Keep changes small and test with `script fixes\run.bat` before rebuilding the exe.
- Quincy is a network engineer and comfortable technically, but new to Python packaging. Explain Windows/PyInstaller steps concretely, with exact paths and commands.
- Commit with clear messages and push to `origin main`.
