"""Call the Notion MCP tool from a small local client."""

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_PARAMETERS = StdioServerParameters(
    command="python",
    args=["notion_server.py"],
)


async def main() -> None:
    async with stdio_client(SERVER_PARAMETERS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "create_research_page",
                arguments={
                    "title": "MCP Connection Test",
                    "content": "# MCP Connection Test\n\n## Result\n\n"
                    "This page was created through the Notion MCP server.",
                },
            )
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
