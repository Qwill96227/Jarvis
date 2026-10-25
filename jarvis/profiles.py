"""Several people sharing one Drexya. Each profile has its own name, home city, notes,
memories and reminders; settings like the API key and voice stay shared.

The 'default' profile is whoever set Drexya up: its name and city are the main settings.
Extra profiles live in the profiles table. Switching resets the conversation so one
person can't ask about another's chat.

Voice identification isn't included: telling voices apart reliably needs a speaker model
that would add hundreds of MB, and a weak one would read out the wrong person's notes.
Saying "this is Marcus" switches instead. A recogniser could call Tools.switch_profile.
"""
from datetime import datetime

DEFAULT = "default"

SCHEMAS = [
    {
        "name": "list_profiles",
        "description": "List the people who have profiles, and which one is active.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "switch_profile",
        "description": "Switch to another person's profile, e.g. when they say 'this is Marcus' or 'switch to "
                       "Marcus'. Each person has their own notes, memories and reminders. The conversation "
                       "starts fresh after switching.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
    {
        "name": "create_profile",
        "description": "Add a profile for a new person sharing this computer, then switch to it.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "home_city": {"type": "string"}},
            "required": ["name"],
        },
    },
]


def profile_id(name: str) -> str:
    return " ".join(name.lower().split())


def all_profiles(store, cfg) -> list:
    """[{'id', 'name', 'home_city'}], the default (main settings) person first."""
    main = {"id": DEFAULT, "name": cfg.get("user_name") or "Main", "home_city": cfg.get("home_city", "")}
    return [main] + store.query("SELECT id, name, home_city FROM profiles ORDER BY created")


def find(store, cfg, name: str):
    """The profile a spoken name refers to, or None."""
    pid = profile_id(name)
    for p in all_profiles(store, cfg):
        if pid in (p["id"], profile_id(p["name"])):
            return p
    return None


class ProfileTools:
    """Mixin for Tools. Needs self.store, self.cfg, self.profile and self.on_profile_switch."""

    def effective_cfg(self) -> dict:
        """Settings with the active person's name and home city filled in."""
        if self.profile == DEFAULT:
            return self.cfg
        row = self.store.query("SELECT name, home_city FROM profiles WHERE id = ?", (self.profile,))
        if not row:
            return self.cfg
        return {**self.cfg, "user_name": row[0]["name"], "home_city": row[0]["home_city"] or self.cfg.get("home_city", "")}

    def switch_profile(self, pid: str):
        self.profile = pid
        self.cfg["active_profile"] = pid
        if self.on_profile_switch:
            self.on_profile_switch(pid)  # the app saves it so it sticks after a restart

    def t_list_profiles(self):
        return [{"name": p["name"], "active": p["id"] == self.profile} for p in all_profiles(self.store, self.cfg)]

    def t_switch_profile(self, name: str):
        p = find(self.store, self.cfg, name)
        if p is None:
            names = ", ".join(x["name"] for x in all_profiles(self.store, self.cfg))
            return f"There's no profile called {name}. Profiles: {names}. I can create one if they'd like."
        if p["id"] == self.profile:
            return f"{p['name']}'s profile is already active."
        self.switch_profile(p["id"])
        return f"Switched to {p['name']}. Greet them by name."

    def t_create_profile(self, name: str, home_city: str = ""):
        name = " ".join(name.split()).strip()
        if not name:
            return "What's their name?"
        if find(self.store, self.cfg, name):
            return f"{name} already has a profile."
        self.store.run("INSERT INTO profiles (id, name, home_city, created) VALUES (?, ?, ?, ?)",
                       (profile_id(name), name, home_city.strip(), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        self.switch_profile(profile_id(name))
        return f"Created a profile for {name} and switched to it."
