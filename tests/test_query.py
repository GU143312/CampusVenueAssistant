import hashlib
import sqlite3
from datetime import date, datetime

import pytest

from domain.query_service import QueryService, TZ, POLICY
from scripts.seed import seed
from storage.repository import connect_readonly


def test_expected_candidates_and_order(service, request_data):
    result = service.search(request_data)
    assert result["ok"]
    data = result["data"]
    assert data["total_matches"] == 16
    candidates = data["candidates"]
    assert (candidates[0]["room_id"], candidates[0]["start_local"]) == ("C301", "2026-10-23T17:30:00+08:00")
    assert {c["room_id"] for c in candidates} == {"C301", "B201", "B203", "B204"}
    assert all(c["capacity"] >= 6 and "projector" in c["equipment"] for c in candidates)
    assert all(c["end_ts"] - c["start_ts"] == 7200 for c in candidates)
    assert all("P003" in c["rule_ids"] for c in candidates)


def test_hard_building_is_never_relaxed(service, request_data):
    result = service.search(request_data | {"required_building":"C", "earliest_start":"15:30", "latest_end":"17:30"})
    assert result["ok"] and result["data"]["candidates"] == []
    assert result["data"]["searched_scope"]["required_building"] == "C"


def test_adjacent_and_cancelled_bookings(service, request_data):
    result = service.search(request_data | {"required_building":"B", "latest_end":"17:30"})
    assert {c["room_id"] for c in result["data"]["candidates"]} == {"B201","B203","B204"}


@pytest.mark.parametrize("start,end", [("15:00","16:00"),("16:00","17:00"),("17:00","18:00"),("15:00","18:00")])
def test_overlap_excluded(service, request_data, start, end):
    duration = 120 if (start,end) == ("15:00","18:00") else 60
    result = service.search(request_data | {"earliest_start":start,"latest_end":end,"duration_minutes":duration})
    assert "C301" not in {c["room_id"] for c in result["data"]["candidates"]}


@pytest.mark.parametrize("patch", [
    {"participants":0}, {"participants":True}, {"participants":6.5},
    {"duration_minutes":45}, {"duration_minutes":150}, {"date_local":"2026-02-30"},
    {"date_local":"2026-10-19"}, {"date_local":"2026-10-27"},
    {"earliest_start":"15:15"}, {"earliest_start":"15:30:01"},
    {"earliest_start":"15:30+08:00"}, {"earliest_start":"07:30"},
    {"latest_end":"22:30"}, {"latest_end":"15:00"},
    {"required_equipment":["teleporter"]}, {"required_building":"X"},
    {"required_equipment":["projector","projector"]}, {"user_id":"admin"},
])
def test_invalid_arguments(service, request_data, patch):
    assert service.search(request_data | patch)["code"] == "INVALID_ARGUMENT"


def test_missing_field_requires_input(service, request_data):
    del request_data["participants"]
    assert service.search(request_data)["code"] == "INVALID_ARGUMENT"


def test_limit_and_stable_ids(service, request_data):
    a = service.search(request_data | {"limit":2})["data"]
    b = service.search(request_data)["data"]
    assert a["truncated"] and a["total_matches"] == b["total_matches"]
    assert a["candidates"] == b["candidates"][:2]


def test_no_match_is_successful_query(service, request_data):
    result = service.search(request_data | {"participants":100})
    assert result["ok"] and result["data"]["total_matches"] == 0


def test_past_slots_filtered(service, request_data):
    result = service.search(request_data | {"date_local":"2026-10-20", "earliest_start":"08:00", "latest_end":"10:00", "duration_minutes":30})
    assert all(c["start_local"] >= "2026-10-20T09:30" for c in result["data"]["candidates"])


def test_sqlite_readonly_and_queries_unchanged(service, db, request_data):
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    con = connect_readonly(db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("DELETE FROM bookings")
    finally:
        con.close()
    service.search(request_data)
    service.schedule("C301", "2026-10-23")
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_missing_database_does_not_become_no_availability(tmp_path, request_data):
    path = tmp_path / "missing.sqlite"
    result = QueryService(path, datetime(2026,10,20,9,tzinfo=TZ)).search(request_data)
    assert result["code"] == "DATA_UNAVAILABLE" and not path.exists()


def test_stale_dataset_and_rule_version(db, request_data):
    s = QueryService(db, datetime(2026,10,26,9,tzinfo=TZ))
    assert s.search(request_data | {"date_local":"2026-10-28"})["code"] == "DATA_OUT_OF_RANGE"
    with sqlite3.connect(db) as con:
        con.execute("UPDATE metadata SET value='old' WHERE key='rule_version'")
    assert QueryService(db, datetime(2026,10,20,9,tzinfo=TZ)).search(request_data)["code"] == "RULE_MISMATCH"


def test_schedule_privacy_and_qualification(service):
    result = service.schedule("C301", "2026-10-23")
    assert result["data"]["busy"] == [{"start_local":"2026-10-23T15:30:00+08:00", "end_local":"2026-10-23T17:30:00+08:00"}]
    assert service.schedule("C304", "2026-10-23")["code"] == "FORBIDDEN"
    assert service.schedule("B205", "2026-10-23")["code"] == "FORBIDDEN"
    assert service.schedule("unknown", "2026-10-23")["code"] == "NOT_FOUND"
    assert service.schedule("C301", "nonsense")["code"] == "INVALID_ARGUMENT"


def test_policy_citations_and_no_match(service):
    hits = service.policies("时长多久")
    assert hits["data"]["clauses"][0]["clause_id"] == "P001"
    assert hits["data"]["clauses"][0]["source"] == "data/policies.json#P001"
    assert not service.policies("xyz-unrelated")["data"]["matched"]
    assert service.policies("", 3)["code"] == "INVALID_ARGUMENT"


def test_seed_is_reproducible_and_guarded(db):
    original = db.read_bytes()
    with pytest.raises(FileExistsError):
        seed(db, date(2026,10,20))
    seed(db, date(2026,10,20), reset=True)
    # Logical fixture reproducibility; SQLite file bookkeeping may change on reset.
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT count(*) FROM rooms").fetchone()[0] == 10
        assert con.execute("SELECT count(*) FROM bookings").fetchone()[0] == 28


def test_policy_config_matches_enforced_contract():
    assert POLICY["rules"] == {"open_hour":8,"close_hour":22,"step_minutes":30,"min_duration":30,"max_duration":120,"horizon_days":7}
