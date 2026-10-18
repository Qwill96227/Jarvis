# Jarvis: project context

Read this first. It explains what this project is, how it's built, where things stand, and what to do next.

## What this is

A J.A.R.V.I.S.-style voice assistant packaged as a **downloadable Windows desktop app**, built by Quincy as a gift for his roommate.

- **Target machine:** the roommate's regular Windows laptop. No GPU, so no local LLMs.
- **Distribution:** a `.exe` built with PyInstaller. The goal is either `JarvisSetup.exe` (an Inno Setup installer) or `Jarvis-Windows.zip`.
- **Repo:** `github.com/Qwill96227/Jarvis` (private, branch `main`)
- **Local working copy:** `C:\Users\Quincy\AI Projects\Jarvis`. The old copy at `E:\Projects\jarvis` is obsolete and can be deleted.

## How it works

```
🎤 mic → Whisper (local, CPU) → text → Claude API (Haiku 5.5 + tools) → reply → Piper TTS (local) → 🔊
```

- **Brain:** Claude API, model `claude-haiku-5-5`. Each user supplies their own API key, entered in the in-app settings and stored in `%APPDATA%\Jarvis\config.json`. The key is **never** bundled in the exe or committed.
- **Speech-to-text:** `faster-whisper`, `base.en` by default (`tiny.en` and `small.en` are selectable). It runs locally on the CPU with int8, and the model downloads on first use (about 140 MB).
- **Text-to-speech:** `piper-tts` with the voice `en_GB-alan-medium`. The voice downloads to `%APPDATA%\Jarvis\voices` on first launch, and the app falls back to the Windows SAPI voice via `pyttsx3` if Piper fails.
- **Trigger:** push-to-talk. The user clicks the reactor core or presses the global hotkey `Ctrl+Alt+J` once to start and again to stop. There's no wake word yet, because always listening drains a laptop battery.
- **Typed messages** get text-only replies. **Voice messages** get spoken replies.

## Code map

The batch scripts live in `script fixes\` and `cd` to the repo root (`%~dp0..`) before running, so the paths inside them are relative to the root.


| File | Purpose |
|---|---|
| `run_jarvis.py` | Entry point. Redirects stdout/stderr to a log when windowed. On crash it shows a MessageBox, prints the traceback, and writes `%APPDATA%\Jarvis\crash.log` |
| `jarvis/app.py` | customtkinter window: the animated "arc reactor" button, transcript, settings dialog, hotkey, threading |
| `jarvis/brain.py` | Claude tool-use loop, system prompt (Jarvis persona, short spoken-style replies), history trimming, error handling |
| `jarvis/tools.py` | Local tools: `get_datetime`, `get_weather` (Open-Meteo, no key), `set_timer`/`list_timers`, `save_note`/`read_notes`/`clear_notes`, `open_website`, `open_app` (Windows allowlist), `media_control` (media keys/volume via `keyboard`), `system_status` (psutil) |
| `jarvis/voice.py` | `Recorder` (sounddevice, 16 kHz mono), `Transcriber` (faster-whisper, loaded in a background thread), `Speaker` (Piper sentence by sentence; Stop button interrupts) |
| `jarvis/config.py` | Settings and paths in `%APPDATA%\Jarvis` |
| `script fixes\run.bat` | Double-click to run from source. Creates `.venv` on first run, reinstalls when `requirements.txt` changes, and keeps the console open on error |
| `script fixes\build.bat` | Builds `dist\Jarvis\Jarvis.exe` with PyInstaller (`--windowed --collect-all ...`), then Inno Setup if installed, otherwise a zip |
| `installer.iss` | Inno Setup script: per-user install, Start menu and desktop shortcuts, optional start-with-Windows |

### Adding a tool
In `jarvis/tools.py`, add a JSON schema to `TOOL_SCHEMAS` and a method named `t_<tool_name>` on `Tools`. `dispatch()` finds it automatically. Claude decides when to call it from the description.

### Important implementation details
- Server-side **web search** uses `{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}`, which can be toggled in settings and costs about 1¢ per search.
- Assistant content is appended to history **exactly as returned**, because web search `encrypted_content` must round-trip. On `pause_turn`, the continuation is **merged into the previous assistant message** rather than appended as a second consecutive assistant turn.
- History trimming only cuts at a plain-text user message, so `tool_use`/`tool_result` pairs never get split.
- On API errors, `_rollback()` restores history to its state before the failed user message.
- All Claude, Whisper, and Piper work runs in background threads. UI updates go through `self.ui(fn, ...)`, which calls `after(0, ...)`.

## Current status (2026-10-17)

- ✅ The code works when run from source: `script fixes\run.bat` opens Jarvis on Quincy's Windows PC.
- ✅ Logic is tested (with a mocked API): the tool loop, `pause_turn` merging, trimming, error rollback, timers, notes, and weather parsing. The GUI rendered correctly in a headless test.
- ✅ **The `.exe` now launches** (2026-10-17). The earlier silent crash was a native access violation (0xC0000005) in a stale **`MSVCP140.dll` 14.31** that PyInstaller bundled; numpy/onnxruntime/ctranslate2 need 14.40+. `build.bat` now copies the current `msvcp140.dll`, `vcruntime140.dll` and `vcruntime140_1.dll` from System32 into `dist\Jarvis\_internal\` after PyInstaller. Native crashes skip Python's handler, so for the next one check Event Viewer → Windows Logs → Application (Event ID 1000) for the faulting module.
- ✅ **Model picker** in settings (`config.MODELS`): Haiku 5.5 (default), Sonnet 5.5, Opus 5.5, Fable 5.1 (warns it burns credits fastest). Non-Haiku models run at `effort: low` with server-side refusal fallback (`fallbacks: "default"`); a refusal is spoken politely. Measured weather-question latency: Haiku 2.9s, Sonnet 3.3s, Opus 4.6s, Fable 4.7s.
- ✅ **Piper playback** synthesizes the whole reply into one clip (+300 ms trailing silence, `latency="high"`) instead of one `sd.play()` per sentence, which caused gaps/crackle/clipped endings. Stop still interrupts. (Sentence-level streaming to TTS was tried and dropped: it only saved ~0.2s.)
- 💡 Voice quality idea, not applied: Microsoft neural voice `en-GB-RyanNeural` via `edge-tts` (online, unofficial, ~1.2s extra latency), with Piper as offline fallback. The `alan-medium` model itself is the main source of the rough sound.
- ✅ `build.bat` zip step retries (antivirus briefly locks fresh files) and fails loudly instead of printing "Done!".
- ⏳ Not yet tested on real hardware: mic capture, Whisper transcription, Piper voice output, media keys, app launching, and the global hotkey.
- ✅ API key is set up on Quincy's PC, saved through the in-app settings to `%APPDATA%\Jarvis\config.json` (never committed). The exe on this PC picks it up automatically; the roommate will enter their own key on first launch.

## Next steps (in order)

1. Rebuild once with the updated `script fixes\build.bat` to confirm the DLL fix and zip step work end to end.
2. Do an end-to-end test on real hardware: typed "hi", then voice weather, a timer, open Spotify/YouTube, volume up, battery, and a web search question.
3. Install Inno Setup 6 and build `Output\JarvisSetup.exe` for the roommate.
4. **v0.2 ideas:** optional "Hey Jarvis" wake word (openWakeWord) as a settings toggle, a system tray icon, Spotify API ("play some Drake"), and Google Calendar/Gmail tools.

## Gotchas

- **`.venv` is git-ignored on purpose.** It's over 1 GB, machine-specific (its absolute path is baked in), and includes files over GitHub's 100 MB limit. Each machine creates its own with `script fixes\run.bat`.
- **PowerShell** needs `.\` before local paths: use `.\.venv\Scripts\python run_jarvis.py`, not `.venv\Scripts\python ...`.
- **`--windowed` exes have no console.** `sys.stdout`/`sys.stderr` are `None`, which is why `run_jarvis.py` redirects them to a log; anything that prints would otherwise crash.
- **Python 3.12 (64-bit)** is the target. `script fixes\build.bat` tries `py -3.12` first.
- **Unsigned exe:** Windows SmartScreen shows "Windows protected your PC". The workaround is More info → Run anyway.
- **Mic permission:** Settings → Privacy & security → Microphone → "Let desktop apps access your microphone" must be on.
- **Never commit** `config.json` or API keys. `.gitignore` covers `config.json`, `*.log`, `build/`, `dist/`, `Output/`, `*.spec`, and `.venv/`.

## Working style for this project

- Keep changes small and test with `script fixes\run.bat` before rebuilding the exe.
- Quincy is a network engineer and comfortable technically, but new to Python packaging. Explain Windows/PyInstaller steps concretely, with exact paths and commands.
- Commit with clear messages and push to `origin main`.
