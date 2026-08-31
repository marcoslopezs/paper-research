"""MCP server that exposes academic paper search as a tool."""

from mcp.server.fastmcp import FastMCP

from main import search_all_papers


mcp = FastMCP("Paper Research")


@mcp.tool()
def search_papers(query: str, max_results: int = 5) -> dict:
    """Search arXiv and Semantic Scholar for papers about a research topic."""
    if not query.strip():
        raise ValueError("The research query cannot be empty.")

    if not 1 <= max_results <= 10:
        raise ValueError("max_results must be between 1 and 10.")

    papers, warnings = search_all_papers(query, max_results)
    return {"papers": papers, "warnings": warnings}


if __name__ == "__main__":
    mcp.run(transport="stdio")
