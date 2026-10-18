# Drexya — a voice assistant for Windows

Click the glowing core (or press **Ctrl+Alt+J** from anywhere), talk, click again. Drexya transcribes you locally, thinks with Claude, and talks back in a British voice.

## What it can do (v0.1)

| Ask | Tool |
|---|---|
| "What's the weather tomorrow?" | Open-Meteo (free, no key) |
| "Set a 12 minute pizza timer" | Local timers, announced out loud |
| "Remember that rent is due on the 3rd" / "What are my notes?" | Notes saved on the laptop |
| "Open Spotify" / "Open YouTube" | App & website launcher |
| "Skip this song" / "Turn it up" | Media keys & volume |
| "How's my battery?" | Laptop status |
| "Who won the game last night?" | Claude web search |
| Anything else | Just conversation |

## Privacy

- Your voice never leaves the laptop. Whisper runs locally; only the transcribed text goes to Claude.
- Settings, notes, and the downloaded voice live in `%APPDATA%\Jarvis`.

## Cost

Runs on **Claude Haiku 5.5** with your own API key. Casual daily use is typically a couple of dollars a month. Web searches are about 1¢ each and can be switched off in settings. You can set a spend limit in the Claude Console.

## First launch

1. Get an API key: https://platform.claude.com (add a few dollars of credit).
2. Paste it into the settings window that pops up, along with your name and city.
3. The first time you talk, it downloads the speech model (~140 MB) and voice (~60 MB). After that it's instant.

Windows SmartScreen may say "Windows protected your PC" because the app isn't code-signed. Click **More info → Run anyway**.

---

## For the builder

### Run from source
Double-click **`script fixes\run.bat`**. The first run creates the `.venv` and installs everything (a few minutes); after that it launches straight away. The `.venv` isn't in git on purpose, because it's machine-specific and over GitHub's size limits.

### Build the installer
Install Python 3.12 (64-bit) and optionally [Inno Setup 6](https://jrsoftware.org/isdl.php), then double-click **`script fixes\build.bat`**.
- With Inno Setup → `Output\DrexyaSetup.exe` (Start menu + desktop shortcut + optional start-with-Windows)
- Without → `Drexya-Windows.zip`

### Project layout
```
jarvis/
  app.py      window, reactor animation, settings, hotkey
  brain.py    Claude tool-use loop + Drexya's personality (system prompt)
  tools.py    weather, timers, notes, apps, media, battery
  voice.py    mic recording, Whisper (speech-to-text), Piper (text-to-speech)
  config.py   settings in %APPDATA%\Jarvis
```

### Adding a skill
In `tools.py`: add a schema to `TOOL_SCHEMAS` and a method named `t_<tool_name>`. That's it. Claude reads the description to decide when to use it.

### Ideas for v0.2
- Wake word ("Hey Drexya") with openWakeWord, behind a settings toggle
- Google Calendar / Gmail tools
- Spotify API for "play some Drake"
- Tray icon so it lives next to the clock
