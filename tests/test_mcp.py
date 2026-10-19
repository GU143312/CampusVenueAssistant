import asyncio
import hashlib
import json
from types import SimpleNamespace

import pytest

from app.mcp_client import decode_result, server_connection


def test_sdk_stdio_actual_roundtrip(db, monkeypatch, request_data):
    monkeypatch.setenv("CAMPUS_DB", str(db))
    monkeypatch.setenv("CAMPUS_NOW", "2026-10-20T09:00:00+08:00")
    before = hashlib.sha256(db.read_bytes()).hexdigest()

    async def run():
        async with server_connection() as server:
            tools = await server.list_tools()
            assert {t.name for t in tools} == {"search_available_rooms","search_policies","get_room_schedule"}
            assert all(t.annotations.readOnlyHint for t in tools)
            result = decode_result(await server.call_tool("search_available_rooms", {"request":request_data}))
            assert result["data"]["total_matches"] == 16
            policies = decode_result(await server.call_tool("search_policies", {"query":"时长"}))
            assert policies["data"]["clauses"][0]["clause_id"] == "P001"
            schedule = decode_result(await server.call_tool("get_room_schedule", {"room_id":"C301","date_local":"2026-10-23"}))
            assert len(schedule["data"]["busy"]) == 1
            denied = await server.call_tool("create_booking", {})
            assert denied.isError
            invalid = await server.call_tool("search_available_rooms", {"request":request_data | {"participants":True}})
            assert invalid.isError
            missing = dict(request_data)
            del missing["date_local"]
            assert (await server.call_tool("search_available_rooms", {"request":missing})).isError
    asyncio.run(run())
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_decoder_text_fallback_and_protocol_error():
    payload = {"schema_version":"campus-booking/v1","ok":True,"code":"OK","data":{},"error":None,"meta":{}}
    result = SimpleNamespace(isError=False,structuredContent=None,content=[SimpleNamespace(type="text",text=json.dumps(payload))])
    assert decode_result(result) == payload
    result.isError = True
    with pytest.raises(ValueError):
        decode_result(result)
