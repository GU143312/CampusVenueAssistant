import hashlib
import json
import os
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from domain.schemas import SearchRequest
from storage.repository import ROOT, connect_readonly

TZ = ZoneInfo("Asia/Macau")
POLICY = json.loads((ROOT / "data/policies.json").read_text(encoding="utf-8"))


def now_local():
    raw = os.environ.get("CAMPUS_NOW")
    now = datetime.fromisoformat(raw) if raw else datetime.now(TZ)
    if now.tzinfo is None:
        raise ValueError("CAMPUS_NOW must include a timezone offset")
    return now.astimezone(TZ)


def envelope(data=None, code="OK", message=None):
    return {"schema_version": "campus-booking/v1", "ok": code == "OK", "code": code,
            "data": data, "error": {"message": message} if message else None,
            "meta": {"rule_version": POLICY["version"], "call_id": str(uuid.uuid4()), "simulated": True}}


class QueryService:
    def __init__(self, db_path: Path | None = None, now=None):
        self.db_path = db_path
        self.now = now or now_local()

    def search(self, payload):
        try:
            req = SearchRequest.model_validate(payload)
        except ValidationError as exc:
            return envelope(code="INVALID_ARGUMENT", message="; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()))
        if not self.now.date() <= req.date_local < self.now.date() + timedelta(days=7):
            return envelope(code="INVALID_ARGUMENT", message="Date must be within today and the next 6 days")
        try:
            con = connect_readonly(self.db_path)
            try:
                metadata = dict(con.execute("SELECT key,value FROM metadata"))
                base = datetime.fromisoformat(metadata["base_date"]).date()
                if metadata["rule_version"] != POLICY["version"]:
                    return envelope(code="RULE_MISMATCH", message="Fixture and policy versions differ; reseed demo")
                if not base <= req.date_local < base + timedelta(days=int(metadata["horizon_days"])):
                    return envelope(code="DATA_OUT_OF_RANGE", message="Requested date is outside the seeded data; reseed demo")
                rooms = [dict(r) for r in con.execute("SELECT * FROM rooms ORDER BY room_id")]
                bookings = [dict(r) for r in con.execute("SELECT room_id,start_ts,end_ts FROM bookings WHERE status='confirmed'")]
            finally:
                con.close()
        except (sqlite3.Error, KeyError, ValueError):
            return envelope(code="DATA_UNAVAILABLE", message="Demo database is missing or invalid; run scripts.seed")

        first = datetime.combine(req.date_local, req.earliest_start, TZ)
        last = datetime.combine(req.date_local, req.latest_end, TZ)
        candidates, excluded = [], Counter()
        for room in rooms:
            equipment = json.loads(room["equipment"])
            reason = (
                "disabled" if not room["enabled"] else
                "qualification" if room["requires_lab"] else
                "capacity" if room["capacity"] < req.participants else
                "equipment" if not set(req.required_equipment) <= set(equipment) else
                "building" if req.required_building and room["building"] != req.required_building else None)
            if reason:
                excluded[reason] += 1
                continue
            start, feasible = first, 0
            while start + timedelta(minutes=req.duration_minutes) <= last:
                end = start + timedelta(minutes=req.duration_minutes)
                start_ts, end_ts = int(start.timestamp()), int(end.timestamp())
                conflict = any(b["room_id"] == room["room_id"] and b["start_ts"] < end_ts and b["end_ts"] > start_ts for b in bookings)
                if start > self.now and not conflict:
                    feasible += 1
                    digest = hashlib.sha256(f"{room['room_id']}:{start_ts}:{end_ts}:{POLICY['version']}".encode()).hexdigest()[:16]
                    candidates.append({"candidate_id": f"cand_{digest}", "room_id": room["room_id"],
                        "building": room["building"], "capacity": room["capacity"], "equipment": equipment,
                        "start_ts": start_ts, "end_ts": end_ts, "start_local": start.isoformat(), "end_local": end.isoformat(),
                        "preferred_building_match": room["building"] == req.preferred_building,
                        "rule_ids": [p["clause_id"] for p in POLICY["clauses"]]})
                start += timedelta(minutes=30)
            if not feasible:
                excluded["no_free_future_slot_in_window"] += 1
        candidates.sort(key=lambda c: (not c["preferred_building_match"], c["start_ts"], c["room_id"]))
        return envelope({"candidates": candidates[:req.limit], "total_matches": len(candidates),
            "truncated": len(candidates) > req.limit, "searched_scope": req.model_dump(mode="json"),
            "excluded_rooms_by_first_reason": dict(excluded), "queried_at": self.now.isoformat(),
            "dataset": metadata["dataset"], "notice": "模拟数据；查询不锁定场地，不会创建预约。"})

    def policies(self, query: str, top_k=3):
        if not isinstance(query, str) or not query.strip() or len(query) > 500 or type(top_k) is not int or not 1 <= top_k <= 5:
            return envelope(code="INVALID_ARGUMENT", message="Provide a query (1-500 characters) and top_k (1-5)")
        q = query.casefold()
        # Transparent lexical baseline, not embedding search or a confidence probability.
        hits = []
        for clause in POLICY["clauses"]:
            score = sum(word in q for word in clause["keywords"])
            if score:
                hits.append({k: v for k, v in clause.items() if k != "keywords"} | {"score": score, "version": POLICY["version"]})
        hits.sort(key=lambda p: (-p["score"], p["clause_id"]))
        return envelope({"clauses": hits[:top_k], "retrieval": "keyword_baseline", "matched": bool(hits)})

    def schedule(self, room_id, date_local):
        try:
            from datetime import date
            d = date.fromisoformat(date_local)
            if not self.now.date() <= d < self.now.date() + timedelta(days=7):
                return envelope(code="INVALID_ARGUMENT", message="Date outside seven-day query horizon")
            con = connect_readonly(self.db_path)
            try:
                meta = dict(con.execute("SELECT key,value FROM metadata"))
                base = date.fromisoformat(meta["base_date"])
                if meta["rule_version"] != POLICY["version"]:
                    return envelope(code="RULE_MISMATCH", message="Fixture and policy versions differ")
                if not base <= d < base + timedelta(days=int(meta["horizon_days"])):
                    return envelope(code="DATA_OUT_OF_RANGE", message="Date outside seeded data")
                room = con.execute("SELECT room_id,enabled,requires_lab FROM rooms WHERE room_id=?", (room_id,)).fetchone()
                if room is None:
                    return envelope(code="NOT_FOUND", message="Unknown room")
                if not room["enabled"] or room["requires_lab"]:
                    return envelope(code="FORBIDDEN", message="Room unavailable to the ordinary demo user")
                start = int(datetime.combine(d, time.min, TZ).timestamp())
                rows = con.execute("SELECT start_ts,end_ts FROM bookings WHERE room_id=? AND status='confirmed' AND start_ts<? AND end_ts>? ORDER BY start_ts", (room_id, start + 86400, start)).fetchall()
                return envelope({"room_id": room_id, "date_local": d.isoformat(), "opening": ["08:00", "22:00"],
                    "busy": [{"start_local": datetime.fromtimestamp(r[0], TZ).isoformat(), "end_local": datetime.fromtimestamp(r[1], TZ).isoformat()} for r in rows]})
            finally:
                con.close()
        except ValueError:
            return envelope(code="INVALID_ARGUMENT", message="Use a valid ISO date YYYY-MM-DD")
        except (sqlite3.Error, KeyError):
            return envelope(code="DATA_UNAVAILABLE", message="Demo database is missing or invalid")
