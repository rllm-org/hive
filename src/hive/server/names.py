from coolname import generate_slug


def generate_name(db) -> str:
    for _ in range(10):
        name = generate_slug(2)
        if db.execute("SELECT 1 FROM agents WHERE id = %s", (name,)).fetchone() is None:
            return name
    raise RuntimeError("Could not generate a unique name after 10 attempts")
