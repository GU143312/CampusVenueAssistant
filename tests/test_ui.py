import asyncio

from app.ui import query_rooms


def test_form_callback_through_mcp(db, monkeypatch):
    monkeypatch.setenv("CAMPUS_DB",str(db))
    monkeypatch.setenv("CAMPUS_NOW","2026-10-20T09:00:00+08:00")
    status, rows, receipt = asyncio.run(query_rooms("2026-10-23","15:30","19:30",120,6,["projector"],"不限","C"))
    assert "16" in status and len(rows) == 5 and receipt["ok"]
    assert rows[0][:5] == ["C301","C",8,"2026-10-23 17:30","2026-10-23 19:30"]
    status, rows, receipt = asyncio.run(query_rooms("2026-10-23","15:30","17:30",120,6,["projector"],"C","C"))
    assert "没有满足" in status and rows == [] and receipt["ok"]


def test_form_invalid_fraction_and_backend_failure(tmp_path, monkeypatch):
    args = ["2026-10-23","15:30","19:30",120,6.5,["projector"],"不限","C"]
    assert asyncio.run(query_rooms(*args))[2]["code"] == "INVALID_ARGUMENT"
    monkeypatch.setenv("CAMPUS_DB",str(tmp_path / "missing.sqlite"))
    monkeypatch.setenv("CAMPUS_NOW","2026-10-20T09:00:00+08:00")
    args[4] = 6
    status, rows, receipt = asyncio.run(query_rooms(*args))
    assert "查询失败" in status and not rows and receipt["code"] == "DATA_UNAVAILABLE"
