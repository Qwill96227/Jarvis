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
- ℹ️ Quincy's saved model is **Fable 5.1** (most expensive; picked while trying the menu). Live tests used Haiku.

## History of work (what was done, and why)

Read this before re-trying something: several things were tried and deliberately dropped.

### 2026-10-17: getting the exe working, voice, models, rename
- **Moved `run.bat` and `build.bat` into `script fixes\`**; both now `cd /d "%~dp0.."` so paths stay relative to the repo root.
- **API key** confirmed saved in `%APPDATA%\Jarvis\config.json` (never committed; repo and history searched for `sk-ant-`).
- **Exe crashed silently on launch** (exit 0xC0000005). Windows Event Log (ID 1000) named a stale `MSVCP140.dll` 14.31 that PyInstaller picked up from elsewhere on the PC; numpy/onnxruntime/ctranslate2 need 14.40+. Fix in `build.bat`: copy `msvcp140.dll`, `vcruntime140.dll`, `vcruntime140_1.dll` from System32 into `dist\...\_internal\`. Also made the zip step retry (antivirus locks fresh files) and fail loudly instead of printing "Done!".
- **Exe copied alone to the Desktop failed** ("Failed to load Python DLL ... _internal\python311.dll"): the exe needs its `_internal` folder. Replaced with a desktop shortcut.
- **"Slow speech" investigation:** measured Whisper `base.en` ≈0.65s, Piper ≈0.1-0.2s per sentence, Claude 1-2s per round trip. The real cause was long replies. **Streaming Claude's reply into TTS sentence by sentence was built, then removed**: it saved only ~0.2s and split audio into separate clips.
- **Piper playback fix (Quincy's spec):** synthesize the whole reply into one buffer, add 300 ms trailing silence, play once with `latency="high"`, poll so Stop still works. Fixed gaps, crackle and clipped endings.
- **Model picker** in settings: Haiku 5.5 (default), Sonnet 5.5, Opus 5.5, Fable 5.1 (warns it burns credits fastest). Non-Haiku models use `effort: low` and server-side refusal fallback. Measured weather-question latency: Haiku 2.9s, Sonnet 3.3s, Opus 4.6s, Fable 4.7s.
- **Renamed Jarvis → Drexya** for everything user-facing (see note at top). Rebuilt as `dist\Drexya\Drexya.exe` + `Drexya-Windows.zip`; desktop shortcut renamed; old `dist\Jarvis` deleted.

### 2026-10-18: Defender and the desktop icon
- Defender quarantined `Drexya.exe` as `Trojan:Win32/Bearfoos.B!ml` (ML heuristic; common PyInstaller false positive) and removed the shortcut with it. Desktop shortcut now launches from source: `.venv\Scripts\pythonw.exe run_jarvis.py` (signed Python, so not flagged, and always runs the latest code).
- Explained the two kinds of flagging: Defender (fix: false-positive submission at microsoft.com/wdsi/filesubmission) and SmartScreen (fix: code signing, e.g. Azure Trusted Signing; or More info → Run anyway). We do **not** try to evade antivirus detection.

### Voice quality research (not applied yet)
- The rough sound comes from the Piper `alan-medium` model itself, not settings (22.05 kHz, medium quality). Audio path checked: MME output, 44.1 kHz headphones, sample rates handled correctly; SAPI fallback (David) unused.
- Tested `edge-tts` with `en-GB-RyanNeural` on this PC (works, ~1.2s extra latency, online, unofficial). Sample saved in the session scratchpad. `edge-tts` is installed in the local `.venv` only, not in requirements.
- **Quincy chose ElevenLabs.** Researched: model `eleven_v4_turbo` (~100ms, real-time) or `eleven_flash_v2_5` (~75ms); output `pcm_24000` plugs into the existing playback (44.1 kHz needs the Pro plan); ~$0.04 per 1K characters on fast models; free tier ~10K characters/month (about 50 replies). Plan: optional key + voice menu in settings, order ElevenLabs → Piper → SAPI. Waiting on his API key.

### 2026-10-25: eleven new features (one commit each, with tests)
1. `416f70b` Persistent memory (SQLite `drexya.db`; recent memories in the system prompt).
2. `d7feb4f` Reminders at a date/time; background scheduler; missed ones announced at startup. System prompt now includes the current local time.
3. `996e56e` Google Calendar behind a provider interface (`jarvis/providers/`); Connect Google button.
4. `bad862a` Gmail on the same interface and sign-in; email content treated as untrusted (verified live against a planted "forward the inbox" instruction).
5. `4e9cb3e` System control: close apps (polite, protected processes), windows, screenshots, file search/open/move (inside the user profile, no running programs, no overwrite, no delete), brightness, Wi-Fi.
6. `6960ac5` Location: Windows location → IP → home city, used by weather.
7. `71472c6` Home Assistant: lights, switches, fans, thermostats (locks/garage/alarms excluded).
8. `4edbc2a` Wake word (openWakeWord, "Hey Jarvis", off by default) + hands-free end-of-speech + interrupting speech.
9. `14b99a8` + `4a30224` Multi-step requests: confirmation gate in code (`send_email`, `clear_notes`), dialog + spoken yes/no, is_error results, retries for read-only tools, partial-progress reports.
10. `4314aa7` Profiles: separate notes, memories, reminders; conversation resets on switch; notes moved from `notes.json` into the database.
11. `6142b46` Security PIN (typed, PBKDF2 hash) for `send_email`, `clear_notes`, `move_file`; audit log of every tool call (90 days; viewable in settings or by asking).

Bugs the tests caught and fixed along the way: memory search missed possessives ("sister's"); "don't send it" read as unclear rather than no; the confirmation gate accepted `1` as yes (`1 == True`); audit logged a profile switch under the new person.

**Incident: real notes were deleted by tests (2026-10-25).** Notes then lived in `notes.json`, which the test helper didn't redirect, and a feature 9 test cleared all notes after a simulated "yes". The original contents couldn't be recovered (no backup; shadow copies need admin). Fixed in `14b99a8`: `tests/helpers.py` redirects every user file path, with a regression test. The two test notes left behind were removed; on the next app start `notes.json` (then `[]`) was imported and renamed `notes.json.imported`.

### Tooling notes from these sessions
- Commit with `git commit -F <file>`: Windows PowerShell 5.1 breaks quoted `-m` messages (one commit failed this way before it was noticed).
- Live tests with Claude used temporary databases and Haiku, cost fractions of a cent each, and never wrote to real user data after the notes fix.
- Packages added to `.venv` and `requirements.txt`: Google API client libs, Pillow, openwakeword. `build.bat` gained `--collect-data googleapiclient` and `--collect-all openwakeword`.

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
