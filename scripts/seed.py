"""Explicit development fixture creation. Never exposed through MCP."""
import argparse
import json
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from storage.repository import ROOT, database_path

TZ = ZoneInfo("Asia/Macau")


def seed(path: Path, base_date: date, reset=False):
    path = path.resolve()
    if path.exists() and not reset:
        raise FileExistsError("Fixture exists; use --reset explicitly to replace demo data")
    path.parent.mkdir(parents=True, exist_ok=True)
    policy = json.loads((ROOT / "data/policies.json").read_text(encoding="utf-8"))
    rooms = [
        ("B201", "B", 8, 1, 0, ["projector", "whiteboard"]),
        ("B202", "B", 4, 1, 0, ["whiteboard"]),
        ("B203", "B", 12, 1, 0, ["projector"]),
        ("B204", "B", 20, 1, 0, ["projector", "video_conference"]),
        ("B205", "B", 8, 0, 0, ["projector"]),
        ("C301", "C", 8, 1, 0, ["projector", "whiteboard"]),
        ("C302", "C", 6, 1, 0, ["whiteboard"]),
        ("C303", "C", 16, 1, 0, ["projector", "video_conference"]),
        ("C304", "C", 10, 1, 1, ["projector"]),
        ("C305", "C", 4, 1, 0, ["projector"]),
    ]
    with sqlite3.connect(path) as con:
        con.executescript("""
        DROP TABLE IF EXISTS bookings;
        DROP TABLE IF EXISTS rooms;
        DROP TABLE IF EXISTS metadata;
        CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE rooms(room_id TEXT PRIMARY KEY, building TEXT NOT NULL,
          capacity INTEGER CHECK(capacity>0), enabled INTEGER NOT NULL,
          requires_lab INTEGER NOT NULL, equipment TEXT NOT NULL);
        CREATE TABLE bookings(booking_id TEXT PRIMARY KEY, room_id TEXT NOT NULL,
          start_ts INTEGER NOT NULL, end_ts INTEGER NOT NULL,
          status TEXT CHECK(status IN ('confirmed','cancelled')), CHECK(start_ts<end_ts));
        CREATE INDEX booking_times ON bookings(room_id,status,start_ts,end_ts);
        """)
        con.executemany("INSERT INTO metadata VALUES (?,?)", [
            ("base_date", base_date.isoformat()), ("rule_version", policy["version"]),
            ("dataset", "simulated_campus_v1"), ("horizon_days", "7")])
        con.executemany("INSERT INTO rooms VALUES (?,?,?,?,?,?)", [(*r[:5], json.dumps(r[5])) for r in rooms])
        for day in range(7):
            d = base_date + timedelta(days=day)
            for room, start, end, status in [
                ("C301", time(15, 30), time(17, 30), "confirmed"),
                ("C303", time(17), time(18), "confirmed"),
                ("B201", time(14), time(15, 30), "confirmed"),
                ("B203", time(15, 30), time(17, 30), "cancelled"),
            ]:
                con.execute("INSERT INTO bookings VALUES (?,?,?,?,?)", (
                    f"demo_{day}_{room}", room,
                    int(datetime.combine(d, start, TZ).timestamp()),
                    int(datetime.combine(d, end, TZ).timestamp()), status))
    return {"dataset": "simulated_campus_v1", "base_date": base_date.isoformat(), "rooms": 10, "booking_rows": 28}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-date", type=date.fromisoformat, default=datetime.now(TZ).date())
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    print(seed(database_path(), args.base_date, args.reset))
