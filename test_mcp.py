"""Call the paper-search MCP tool from a small local client."""

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_PARAMETERS = StdioServerParameters(
    command="python",
    args=["paper_server.py"],
)


async def main() -> None:
    async with stdio_client(SERVER_PARAMETERS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Available tools:")
            for tool in tools.tools:
                print(f"- {tool.name}: {tool.description}")

            result = await session.call_tool(
                "search_papers",
                arguments={"query": "quantum computing", "max_results": 3},
            )
            print("\nTool result:")
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
