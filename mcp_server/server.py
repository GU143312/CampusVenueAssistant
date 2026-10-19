from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from domain.query_service import QueryService
from domain.schemas import SearchRequest

mcp = FastMCP("campus-readonly")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


@mcp.tool(annotations=READ)
def search_available_rooms(request: SearchRequest) -> dict:
    """Query simulated future slots. All hard constraints are enforced; no booking is made.
    Times use Asia/Macau (UTC+08). Required equipment may explicitly be [].
    Missing fields must be clarified. Only preferred_building is a soft preference.
    """
    return QueryService().search(request.model_dump(mode="json"))


@mcp.tool(annotations=READ)
def search_policies(query: str, top_k: int = 3) -> dict:
    """Retrieve simulated policy clauses by keyword. No match is not evidence of no restriction."""
    return QueryService().policies(query, top_k)


@mcp.tool(annotations=READ)
def get_room_schedule(room_id: str, date_local: str) -> dict:
    """Read occupied intervals for an eligible room. No occupant names or user identifiers."""
    return QueryService().schedule(room_id, date_local)


if __name__ == "__main__":
    # stdout belongs exclusively to MCP protocol traffic.
    mcp.run(transport="stdio")
