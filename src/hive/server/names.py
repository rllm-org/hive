import random
import sqlite3

_ADJECTIVES = [
    "swift", "quiet", "bold", "sharp", "bright", "dark", "deep", "cold",
    "wild", "calm", "vast", "lost", "lone", "free", "wise", "keen",
    "pure", "raw", "old", "new", "high", "low", "fast", "slow",
    "iron", "gold", "silver", "crimson", "azure", "ember", "frost", "storm",
    "hollow", "sacred", "ancient", "silent", "endless", "hidden", "wandering",
    "fallen", "risen", "burning", "frozen", "shining", "distant", "forgotten",
    "electric", "magnetic", "cosmic", "lunar", "solar",
]

_NOUNS = [
    "phoenix", "atlas", "cipher", "nexus", "vortex", "oracle", "specter",
    "titan", "herald", "forge", "beacon", "vertex", "prism", "zenith",
    "nadir", "apex", "nova", "pulsar", "quasar", "nebula", "comet",
    "hydra", "sphinx", "kraken", "chimera", "dragon", "raven", "falcon",
    "wolf", "lynx", "hawk", "bear", "lion", "serpent", "eagle",
    "oak", "cedar", "thorn", "ember", "stone", "river", "summit",
    "canyon", "glacier", "tempest", "current", "horizon", "abyss", "shore",
]


def generate_name(db: sqlite3.Connection) -> str:
    for _ in range(10):
        name = f"{random.choice(_ADJECTIVES)}-{random.choice(_NOUNS)}"
        row = db.execute("SELECT 1 FROM agents WHERE id = ?", (name,)).fetchone()
        if row is None:
            return name
    raise RuntimeError("Could not generate a unique name after 10 attempts")


def generate_name_with_preference(preferred: str, db: sqlite3.Connection) -> str:
    row = db.execute("SELECT 1 FROM agents WHERE id = ?", (preferred,)).fetchone()
    if row is None:
        return preferred
    for _ in range(10):
        name = f"{random.choice(_ADJECTIVES)}-{preferred}"
        row = db.execute("SELECT 1 FROM agents WHERE id = ?", (name,)).fetchone()
        if row is None:
            return name
    raise RuntimeError("Could not generate a unique name after 10 attempts")
