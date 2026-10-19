import asyncio
import hashlib
import json
from importlib.metadata import version

from app.mcp_client import decode_result, server_connection
from storage.repository import database_path


async def main():
    before = hashlib.sha256(database_path().read_bytes()).hexdigest()
    async with server_connection() as server:
        tools = await server.list_tools()
        request = {"date_local":"2026-10-23","earliest_start":"15:30","latest_end":"19:30",
            "duration_minutes":120,"participants":6,"required_equipment":["projector"],"preferred_building":"C"}
        policy = decode_result(await server.call_tool("search_policies", {"query":"时长和投影"}))
        result = decode_result(await server.call_tool("search_available_rooms", {"request":request}))
        assert result["ok"] and result["data"]["candidates"][0]["room_id"] == "C301"
        assert result["data"]["total_matches"] == 16
        assert hashlib.sha256(database_path().read_bytes()).hexdigest() == before
        print(json.dumps({"verification":"offline SDK MCP stdio; no model call", "versions":{n:version(n) for n in ["openai-agents","mcp","pydantic","gradio"]},
            "tools":[t.name for t in tools], "database_unchanged":True,"database_sha256":before,
            "policy_receipt":policy,"query_receipt":result},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    asyncio.run(main())
