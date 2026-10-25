"""Long-term memory: preferences and facts about the user that last across sessions.

Different from notes: notes are things the user wants kept and read back; memories are
things Drexya should know about the user ("prefers Celsius", "sister is called Ana").
The most recent memories are also put in the system prompt, so Drexya uses them
without having to call recall first.
"""
from datetime import datetime

CATEGORIES = ["preference", "fact", "person", "other"]

SCHEMAS = [
    {
        "name": "remember",
        "description": "Save a lasting preference or fact about the user so you know it in future "
                       "conversations. Use when the user asks you to remember something, or tells you "
                       "something about themselves that will stay true (likes, routines, people, places). "
                       "Don't save one-off details from the current conversation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string",
                         "description": "The fact as a short third-person sentence, e.g. 'Prefers Celsius'."},
                "category": {"type": "string", "enum": CATEGORIES},
            },
            "required": ["text"],
        },
    },
    {
        "name": "recall",
        "description": "Search what you remember about the user. Leave query empty to list everything.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Words to look for, e.g. 'sister'."}},
        },
    },
    {
        "name": "forget",
        "description": "Delete a remembered item. Pass the id from recall, or words that identify it. "
                       "If several items match, you get them back and should ask which one.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "query": {"type": "string"},
            },
        },
    },
]

RECALL_LIMIT = 25
STOPWORDS = {"what", "who", "where", "when", "the", "and", "you", "your", "about", "remember",
             "know", "does", "did", "are", "was", "have", "that", "this", "for", "with"}


def _word(token: str) -> str:
    token = token.strip(".,!?;:\"()")
    return token[:-2] if token.endswith(("'s", "’s")) else token


def _match(store, profile: str, query: str) -> list:
    rows = store.query(
        "SELECT id, category, text, saved FROM memories WHERE profile = ? AND text LIKE ? ORDER BY id",
        (profile, f"%{query}%"),
    )
    if rows:
        return rows
    # No exact phrase match: fall back to any meaningful word ("my sister's name" -> sister, name)
    words = [w for w in (_word(t) for t in query.lower().split()) if len(w) > 2 and w not in STOPWORDS]
    if not words:
        return []
    where = " OR ".join("lower(text) LIKE ?" for _ in words)
    return store.query(
        f"SELECT id, category, text, saved FROM memories WHERE profile = ? AND ({where}) ORDER BY id",
        (profile, *[f"%{w}%" for w in words]),
    )


def summary(store, profile: str, limit: int = 40) -> list:
    """Most recent memories, oldest first, for the system prompt."""
    rows = store.query(
        "SELECT text FROM memories WHERE profile = ? ORDER BY id DESC LIMIT ?", (profile, limit))
    return [r["text"] for r in reversed(rows)]


class MemoryTools:
    """Mixin for Tools. Needs self.store and self.profile."""

    def t_remember(self, text: str, category: str = "fact"):
        text = text.strip()
        if not text:
            return "Nothing to remember."
        if category not in CATEGORIES:
            category = "other"
        if self.store.query("SELECT 1 FROM memories WHERE profile = ? AND lower(text) = lower(?)",
                            (self.profile, text)):
            return "I already knew that."
        self.store.run(
            "INSERT INTO memories (profile, category, text, saved) VALUES (?, ?, ?, ?)",
            (self.profile, category, text, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        return "Got it, I'll remember that."

    def t_recall(self, query: str = ""):
        query = query.strip()
        if query:
            rows = _match(self.store, self.profile, query)
        else:
            rows = self.store.query(
                "SELECT id, category, text, saved FROM memories WHERE profile = ? ORDER BY id",
                (self.profile,))
        if not rows:
            return "Nothing remembered about that." if query else "I don't have anything remembered yet."
        return rows[:RECALL_LIMIT]

    def t_forget(self, id: int = None, query: str = ""):
        if id is not None:
            gone = self.store.run("DELETE FROM memories WHERE profile = ? AND id = ?", (self.profile, id))
            return "Forgotten." if gone else f"There's no memory with id {id}."
        query = query.strip()
        if not query:
            return "Tell me what to forget."
        rows = _match(self.store, self.profile, query)
        if not rows:
            return "I don't have anything matching that."
        if len(rows) > 1:
            return {"several_match": rows[:RECALL_LIMIT],
                    "note": "Ask the user which one, then call forget with its id."}
        self.store.run("DELETE FROM memories WHERE id = ?", (rows[0]["id"],))
        return f"Forgotten: {rows[0]['text']}"
