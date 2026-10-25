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
| "Any new email?" / "Summarize my inbox" / "Email ana@example.com saying yes to dinner" | Gmail (optional; always asks before sending) |
| "Close Spotify" / "What windows are open?" / "Switch to Chrome" | Window and app control |
| "Take a screenshot" / "Find my resume" / "Open it" / "Move it to Documents" | Screenshots and files |
| "Brightness to 40" / "Am I on Wi-Fi?" / "Connect to HomeNet" | Screen brightness (laptops) and Wi-Fi |
| "Where am I?" / "What's the weather?" (no city) | Location awareness |
| "Turn the kitchen lights to 40%" / "Turn off the coffee maker" / "Set the heat to 72" | Home Assistant (optional) |
| "Hey Jarvis, …" (hands-free) / say it again to interrupt | Wake word (optional) |
| "This is Marcus" / "Add a profile for Ana" / "Switch back to Quincy" | Profiles for people sharing the laptop |
| "What have you done today?" | Activity log (every action is recorded) |
| Anything else | Just conversation |

## Memory

Drexya remembers lasting preferences and facts you tell it ("I prefer Celsius", "my sister is Ana") and uses them in later chats. Ask "what do you remember about me?" to see them, or "forget that" to remove one. Memories are stored on the laptop in `%APPDATA%\Jarvis\drexya.db`, and the most recent 40 are included with each request to Claude. Turn it off in settings with **Remember things about me between chats**.

## Reminders

Timers are quick countdowns that end if Drexya is closed. Reminders are for a date and time ("Friday at 6pm"): they're saved in `drexya.db`, survive restarts, and any that came due while Drexya was closed are announced the next time it starts ("While I was off, you had a reminder…"). Drexya needs to be running for a reminder to go off on time, so tick **Start Drexya when Windows starts** in the installer if you rely on them. To switch reminders off, set `"reminders_enabled": false` in `%APPDATA%\Jarvis\config.json`.

## System control

Drexya can close apps, list and switch windows, take screenshots (saved to `Pictures\Screenshots`), find, open and move files, set the screen brightness and manage Wi-Fi. Safety limits:

- **Closing apps** works like clicking X, so apps with unsaved work still ask to save. Core Windows processes are off-limits.
- **Files:** only inside your user folder. `open_file` opens documents, pictures and folders but never runs programs or scripts (`.exe`, `.bat`, `.ps1`, …), so a malicious email or web page can't use Drexya to launch something. Moving never overwrites a file, and there is no delete.
- **Brightness** works on laptop screens; most external monitors don't allow software control.
- **Wi-Fi** can report status, list saved networks, connect to a network the PC has joined before, and disconnect. Turning the Wi-Fi radio off needs admin rights, so it isn't included.

Switch it all off with `"system_control_enabled": false` in `%APPDATA%\Jarvis\config.json`.

## Location

When you ask for the weather without naming a place, Drexya works out where you are. Choose how in settings under **Location for weather**:

| Setting | How it works |
|---|---|
| **Detect automatically** (default) | Windows Location first (GPS/Wi-Fi, most accurate), then your IP address, then your home city |
| **Use my IP address** | IP lookup (city-level), then home city |
| **Always use my home city** | Nothing leaves the PC |

- **Windows Location** has to be allowed: Settings → Privacy & security → Location → turn on **Location services** and **Let desktop apps access your location**. If it's off, Drexya skips straight to the IP lookup.
- **IP lookups can be wrong**, sometimes by hundreds of miles: VPNs, mobile hotspots and some internet providers report a different city. Drexya always names the place it used ("In Seattle…"), so you'll notice; if it's wrong, allow Windows Location or pick **Always use my home city**.
- Privacy: the IP lookup uses ipinfo.io and turning coordinates into a city name uses BigDataCloud; both see your IP address. The location is remembered for 10 minutes.

## Security PIN and activity log

**PIN.** In settings, set a **Security PIN** (4–8 digits). From then on, sending email, deleting all notes and moving files need the PIN typed into the confirmation box, as well as a yes. It has to be typed, not spoken, so nobody nearby overhears it. Three wrong tries cancels the action. The PIN is stored only as a salted hash (PBKDF2) in `config.json`, never as the digits themselves. To change it, type a new one; to remove it, tick **Remove PIN**. Which actions need it: `"pin_tools"` in `config.json`.

**Activity log.** Every action Drexya takes is recorded with the time, the person, what it did, the details and the outcome (done, error, declined or wrong PIN). Long text is shortened and anything that looks like a token or password is masked. See it with **View activity log** in settings, or ask "What have you done today?" (which shows only the active person's actions). Entries older than 90 days are deleted automatically (`"audit_days"`); turn logging off with `"audit_enabled": false`. It's stored in `drexya.db` on the laptop.

## Profiles (sharing the laptop)

Each person gets their own name, home city, **notes, memories and reminders**. The API key, voice, model and connected accounts are shared.

- **Switch by voice:** "This is Marcus", "Switch to Marcus", or "Add a profile for Ana". Or use **Who's using Drexya** in settings (with **+ Add person**), where you can also edit each person's name and city.
- The active person is remembered after a restart. Drexya starts a fresh conversation whenever the person changes, so nobody can ask about someone else's chat.
- Reminders still go off whoever is active, and Drexya says whose they are ("Marcus, a reminder: gym").
- The first person (whoever set Drexya up) uses the main **name** and **home city** settings.
- **Voice identification isn't included.** Telling voices apart reliably needs a speaker-recognition model that would add hundreds of MB to the app, and an unreliable one would read out the wrong person's notes. Just say who you are.
- Notes now live in `drexya.db` alongside everything else; an old `notes.json` is imported automatically (and renamed `notes.json.imported`).

## Multi-step requests and confirmations

Drexya can do several things from one request ("note buy milk, remind me tomorrow at 8, and email Ana that I'll bring it"), then sum up in a sentence.

- **Confirmation before irreversible actions.** Sending email and deleting all notes always ask first, in a dialog showing exactly what will happen. If you asked by voice, Drexya also asks out loud and you can just say yes or no. Silence, an unclear answer, or a minute with no answer all count as **no**. This check is in Drexya's code, so the AI can't skip it. To make other actions ask too, add them to `"confirm_tools"` in `config.json`, e.g. `["send_email", "clear_notes", "move_file", "close_app"]`.
- **When something fails,** Drexya tries another way once if there is one, otherwise says what worked and what didn't. Lookups (weather, email, calendar) retry once after a network blip; actions are never retried automatically, so nothing happens twice.
- **If the connection drops midway,** Drexya tells you what it had already done ("I lost my internet connection. Before that, I'd started the timer.") and remembers it, so asking again won't repeat those steps.
- One request can take up to 12 steps (`"max_tool_steps"` in `config.json`).

## Wake word and interrupting

Turn on **Listen for a wake word** in settings and Drexya listens for a phrase, then records until you stop talking, with no clicking needed. Choices: **Hey Jarvis** (default), **Alexa**, **Hey Mycroft**.

- **Interrupting:** while Drexya is talking, say the wake word, press the hotkey or click the core to cut it off and start listening.
- **Privacy:** listening runs entirely on the laptop with [openWakeWord](https://github.com/dscripka/openWakeWord). Audio is checked in 80 ms pieces and never stored or sent; nothing goes to Claude until after the wake word.
- **Battery:** always-on listening uses some CPU continuously, which is why it's off by default.
- **Tuning:** if it triggers by mistake, raise `"wake_word_threshold"` in `%APPDATA%\Jarvis\config.json` (e.g. 0.7); if it misses you, lower it (e.g. 0.35).
- **A custom "Hey Drexya":** there's no ready-made model for it, but openWakeWord's free training notebook (linked from its GitHub page) can make one in about an hour. Save the `.onnx` file somewhere on the laptop and set `"wake_word"` to its full path in `config.json`.
- The models (a few MB) download to `%APPDATA%\Jarvis\wakeword` the first time it's switched on.

## Smart home (Home Assistant)

If you run [Home Assistant](https://www.home-assistant.io), Drexya can list devices, switch lights, switches and fans on and off, dim lights, and set thermostats.

1. In Home Assistant, click your **profile** (bottom left) → **Security** tab → **Long-lived access tokens** → **Create token**. Name it "Drexya" and copy it (it's only shown once).
2. In Drexya's settings, fill in **Home Assistant address** (e.g. `http://homeassistant.local:8123`, or `http://192.168.1.50:8123`) and paste the **access token**. Save.
3. Ask "what devices do you see?" to check it works.

Drexya uses the device names from Home Assistant ("Kitchen Light"), so name things the way you'd say them. If a name matches more than one device ("bedroom"), Drexya asks which. **Locks, garage doors, alarms and cameras are deliberately not controllable**: unlocking a door by voice needs more safeguards than Drexya has. The token is stored in `config.json` on the laptop.

## Connecting Google (calendar and Gmail)

Drexya talks to Google with your own free Google Cloud "OAuth client". One-time setup, about 10 minutes:

1. Go to https://console.cloud.google.com, sign in, and create a project (e.g. "Drexya").
2. **APIs & Services → Library**: search for and **Enable** the **Google Calendar API** and/or the **Gmail API**.
3. **Google Auth Platform** (OAuth consent screen): choose **External**, give it a name and your email. Under **Audience → Test users**, add the Google account(s) that will use Drexya.
4. **Clients → Create client → Application type: Desktop app → Create**, then **Download JSON**.
5. Save that file as `%APPDATA%\Jarvis\google_client.json` (paste `%APPDATA%\Jarvis` into File Explorer's address bar to open the folder).
6. In Drexya: ⚙ settings → choose **Calendar: Google Calendar** and/or **Email: Gmail** → **Connect Google**. Your browser opens; sign in and allow access. Then click **Save**.

Good to know:
- While the Google project is in **Testing**, Google makes you reconnect every 7 days. To stop that, click **Publish app** on the Audience page. Google then shows an "unverified app" screen when you connect; click **Advanced → Go to Drexya**. That's expected for a personal app.
- Permissions requested: read and add calendar events; read Gmail and send mail as you. Drexya can't delete or archive email. If you turn on Gmail after connecting for the calendar, click **Connect Google** again so Google can grant the extra permission.
- **Sending email:** Drexya always shows you the email and waits for your yes (see Multi-step requests and confirmations). It needs an actual address ("ana@example.com"); it won't guess one from a name.
- **Suspicious emails:** email text is treated as information, never as instructions, so a message saying "AI, forward this inbox to…" is ignored and pointed out to you.
- The sign-in is saved in `%APPDATA%\Jarvis\google_token.json`; delete that file to disconnect.
- Never commit or share `google_client.json` or `google_token.json`. For a second person, add them as a test user (step 3) and give them the client file privately, or have them make their own.
- Calendar and email sit behind provider interfaces (`jarvis/providers/`), so Outlook can be added later without changing the tools.

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
  email_tools.py     email tools (provider-agnostic; send needs confirmation)
  system_tools.py    close apps, windows, screenshots, files, brightness, Wi-Fi
  location.py        current location: Windows location -> IP -> home city
  home_assistant.py  lights, switches, fans, thermostats via Home Assistant's REST API
  wakeword.py        always-on wake word listener + end-of-speech detection
  safety.py          confirmation/PIN rules, spoken yes/no, PIN hashing, audit log
  profiles.py        people sharing the laptop: list / switch / create
  providers/  base.py interfaces, google.py (OAuth, Google Calendar, Gmail); add outlook.py later
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
