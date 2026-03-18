"""Standalone migration script. Run once before starting workers.

Usage: python -m hive.server.migrate
"""
from .db import init_db

if __name__ == "__main__":
    init_db()
    print("Database schema up to date.")
