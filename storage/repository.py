import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def database_path():
    return Path(os.environ.get("CAMPUS_DB") or ROOT / "data" / "demo.sqlite").resolve()


def connect_readonly(path=None):
    path = Path(path or database_path()).resolve()
    # mode=ro also prevents silently creating a missing database.
    con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con
