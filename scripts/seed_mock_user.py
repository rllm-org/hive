"""Ensure a local-dev password user exists (login without signup / verification).

Run with: uv run python scripts/seed_mock_user.py

Override defaults: HIVE_MOCK_EMAIL, HIVE_MOCK_PASSWORD, HIVE_MOCK_HANDLE
"""
import os
import uuid
from datetime import datetime, timezone

import bcrypt
import psycopg

from hive.server.db import DATABASE_URL

MOCK_EMAIL = os.environ.get("HIVE_MOCK_EMAIL", "dev@hive.local")
MOCK_PASSWORD = os.environ.get("HIVE_MOCK_PASSWORD", "hivehive12")
MOCK_HANDLE = os.environ.get("HIVE_MOCK_HANDLE", "hive-mock-dev")


def main() -> None:
    hashed = bcrypt.hashpw(MOCK_PASSWORD.encode(), bcrypt.gensalt()).decode()
    now = datetime.now(timezone.utc)
    new_uuid = str(uuid.uuid4())

    with psycopg.connect(DATABASE_URL, autocommit=False) as conn:
        conn.execute(
            """
            INSERT INTO users (email, handle, password, role, created_at, uuid)
            VALUES (%s, %s, %s, 'user', %s, %s)
            ON CONFLICT (email) DO UPDATE SET
                password = EXCLUDED.password,
                handle = EXCLUDED.handle
            """,
            (MOCK_EMAIL, MOCK_HANDLE, hashed, now, new_uuid),
        )
        conn.commit()

    print(f"Mock user: email={MOCK_EMAIL}  password={MOCK_PASSWORD}  handle={MOCK_HANDLE}")


if __name__ == "__main__":
    main()
