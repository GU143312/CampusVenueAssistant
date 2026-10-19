import json
import os
import sys

from agents.mcp import MCPServerStdio
from pydantic import BaseModel, ConfigDict

from storage.repository import ROOT


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    ok: bool
    code: str
    data: dict | None
    error: dict | None
    meta: dict


def server_connection():
    env = {k: os.environ[k] for k in ("CAMPUS_DB", "CAMPUS_NOW") if os.environ.get(k)}
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    return MCPServerStdio(name="campus-readonly", params={
        "command": sys.executable, "args": ["-m", "mcp_server.server"], "cwd": str(ROOT), "env": env,
    }, client_session_timeout_seconds=10, cache_tools_list=True)


def decode_result(result):
    if result.isError:
        raise ValueError("MCP rejected the tool request; inspect required fields and types")
    payload = result.structuredContent
    if payload is None:
        texts = [c.text for c in result.content if c.type == "text"]
        if len(texts) != 1:
            raise ValueError("Expected one JSON envelope")
        payload = json.loads(texts[0])
    decoded = Envelope.model_validate(payload)
    if decoded.schema_version != "campus-booking/v1" or decoded.ok != (decoded.code == "OK"):
        raise ValueError("Inconsistent or unsupported response envelope")
    return decoded.model_dump()


async def call_tool(name, arguments):
    async with server_connection() as server:
        return decode_result(await server.call_tool(name, arguments))
