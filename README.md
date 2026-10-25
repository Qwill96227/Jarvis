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
| "Remember I take my coffee black" / "What do you know about me?" / "Forget that" | Long-term memory |
| "Remind me tomorrow at 9 to call the dentist" / "What reminders do I have?" / "Cancel the trash one" | Reminders (survive restarts) |
| "What's on my calendar tomorrow?" / "Add lunch with Sam Friday at noon" | Google Calendar (optional, see below) |
| Anything else | Just conversation |

## Memory

Drexya remembers lasting preferences and facts you tell it ("I prefer Celsius", "my sister is Ana") and uses them in later chats. Ask "what do you remember about me?" to see them, or "forget that" to remove one. Memories are stored on the laptop in `%APPDATA%\Jarvis\drexya.db`, and the most recent 40 are included with each request to Claude. Turn it off in settings with **Remember things about me between chats**.

## Reminders

Timers are quick countdowns that end if Drexya is closed. Reminders are for a date and time ("Friday at 6pm"): they're saved in `drexya.db`, survive restarts, and any that came due while Drexya was closed are announced the next time it starts ("While I was off, you had a reminder…"). Drexya needs to be running for a reminder to go off on time, so tick **Start Drexya when Windows starts** in the installer if you rely on them. To switch reminders off, set `"reminders_enabled": false` in `%APPDATA%\Jarvis\config.json`.

## Connecting Google (calendar)

Drexya talks to Google with your own free Google Cloud "OAuth client". One-time setup, about 10 minutes:

1. Go to https://console.cloud.google.com, sign in, and create a project (e.g. "Drexya").
2. **APIs & Services → Library**: search for and **Enable** the **Google Calendar API**.
3. **Google Auth Platform** (OAuth consent screen): choose **External**, give it a name and your email. Under **Audience → Test users**, add the Google account(s) that will use Drexya.
4. **Clients → Create client → Application type: Desktop app → Create**, then **Download JSON**.
5. Save that file as `%APPDATA%\Jarvis\google_client.json` (paste `%APPDATA%\Jarvis` into File Explorer's address bar to open the folder).
6. In Drexya: ⚙ settings → **Calendar: Google Calendar** → **Connect Google**. Your browser opens; sign in and allow access. Then click **Save**.

Good to know:
- While the Google project is in **Testing**, Google makes you reconnect every 7 days. To stop that, click **Publish app** on the Audience page. Google then shows an "unverified app" screen when you connect; click **Advanced → Go to Drexya**. That's expected for a personal app.
- Drexya only asks for permission to read and add calendar events. The sign-in is saved in `%APPDATA%\Jarvis\google_token.json`; delete that file to disconnect.
- Never commit or share `google_client.json` or `google_token.json`. For a second person, add them as a test user (step 3) and give them the client file privately, or have them make their own.
- The calendar code sits behind a provider interface (`jarvis/providers/`), so Outlook can be added later without changing the tools.

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
  tools.py    weather, timers, notes, apps, media, battery; inherits the feature mixins below
  memory.py   remember / recall / forget
  reminders.py  set / list / cancel reminders + background scheduler
  calendar_tools.py  calendar tools (provider-agnostic)
  providers/  base.py interfaces, google.py (OAuth + Google Calendar); add outlook.py later
  storage.py  SQLite database (%APPDATA%\Jarvis\drexya.db)
  voice.py    mic recording, Whisper (speech-to-text), Piper (text-to-speech)
  config.py   settings in %APPDATA%\Jarvis
tests/        unit tests: .\.venv\Scripts\python -m unittest discover -s tests -t .
```

### Adding a skill
In `tools.py`: add a schema to `TOOL_SCHEMAS` and a method named `t_<tool_name>`. That's it. Claude reads the description to decide when to use it. Bigger features get their own module with a `SCHEMAS` list and a mixin class of `t_` methods that `Tools` inherits; `Tools.schemas()` decides which groups are sent based on settings.

### Ideas for v0.2
- Wake word ("Hey Drexya") with openWakeWord, behind a settings toggle
- Google Calendar / Gmail tools
- Spotify API for "play some Drake"
- Tray icon so it lives next to the clock
