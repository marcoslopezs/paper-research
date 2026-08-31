"""A local LLM agent that can search for academic papers through MCP."""

import asyncio
import json
from pathlib import Path
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


MODEL = "gemma4:e2b"
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_TIMEOUT_SECONDS = 300
MAX_TOOL_ROUNDS = 3
MAX_PAPERS_FOR_MODEL = 7
MAX_ABSTRACT_CHARACTERS = 400
SHOW_TOOL_TRACE = True

SERVER_PARAMETERS = StdioServerParameters(
    command="python",
    args=["paper_server.py"],
)
NOTION_SERVER_PARAMETERS = StdioServerParameters(
    command="python",
    args=["notion_server.py"],
)


def ask_ollama(messages: list[dict], tools: list[dict]) -> dict:
    """Send the conversation and available tools to the local Ollama server."""
    request_body = json.dumps(
        {
            "model": MODEL,
            "messages": messages,
            "tools": tools,
            "stream": False,
        }
    ).encode("utf-8")
    request = Request(
        OLLAMA_CHAT_URL,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except URLError as error:
        raise RuntimeError(
            "Could not reach Ollama. Make sure the Ollama application is running."
        ) from error
    except TimeoutError as error:
        raise RuntimeError(
            "The local model took too long to respond. Try a shorter topic or wait for "
            "the model to finish loading."
        ) from error


def mcp_tools_to_ollama_tools(mcp_tools: list) -> list[dict]:
    """Convert MCP tool metadata into the schema expected by Ollama."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


def compact_tool_result(tool_result_text: str) -> str:
    """Keep the tool result small enough for the local model's context window."""
    data = json.loads(tool_result_text)
    compact_papers = []

    for paper in data["papers"][:MAX_PAPERS_FOR_MODEL]:
        compact_papers.append(
            {
                "title": paper["title"],
                "authors": paper["authors"],
                "year": paper["year"],
                "abstract": paper["abstract"][:MAX_ABSTRACT_CHARACTERS],
                "url": paper["url"],
                "source": paper["source"],
            }
        )

    return json.dumps({"papers": compact_papers, "warnings": data["warnings"]})


async def research(question: str) -> tuple[str, list[dict]]:
    """Let the local model decide whether to call the paper-search MCP tool."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are a research assistant in a one-shot command-line program. "
                "For every research question, call the paper-search tool first. After "
                "it returns, write a Markdown research report based only on the returned "
                "titles, abstracts, authors, years, and URLs. Do not add general "
                "background knowledge or claims that are not supported by those results. "
                "Use exactly these sections: # [topic], ## Scope and Evidence, ## "
                "Executive Summary, ## Introduction, ## Technology or Theme Description, "
                "## Advantages and Potential Benefits, ## Disadvantages and Limitations, "
                "## Current Research Topics, ## Selected Papers, ## Comparison, ## "
                "Research Gaps. Write two to four detailed paragraphs in "
                "Technology or Theme Description, but only when the retrieved abstracts "
                "support them. Number the sources [1], [2], and so on in the order returned. "
                "Every factual statement in all prose sections must cite one or more of "
                "these source numbers. If the abstracts do not support an advantage, "
                "disadvantage, or other claim, state that the retrieved evidence is "
                "insufficient instead of inventing information. In Selected Papers, include "
                "each paper's exact title, authors, year, source, URL, and an "
                "abstract-based contribution with citations. State that the evidence comes "
                "from abstracts in Scope and Evidence. Do not write a Sources section; "
                "the application adds it from the retrieved paper data. Do not ask a "
                "follow-up question, offer more help, or end with a question."
            ),
        },
        {"role": "user", "content": question},
    ]
    used_tool = False
    retrieved_papers = []

    async with stdio_client(SERVER_PARAMETERS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tool_result = await session.list_tools()
            ollama_tools = mcp_tools_to_ollama_tools(tool_result.tools)

            for _ in range(MAX_TOOL_ROUNDS):
                response = ask_ollama(messages, ollama_tools)
                assistant_message = response["message"]
                messages.append(assistant_message)
                tool_calls = assistant_message.get("tool_calls", [])

                if not tool_calls:
                    if not used_tool:
                        raise RuntimeError("The model did not use the paper-search tool.")
                    return (
                        assistant_message.get("content", "The model returned no answer."),
                        retrieved_papers,
                    )

                for tool_call in tool_calls:
                    used_tool = True
                    function = tool_call["function"]
                    arguments = function["arguments"].copy()
                    arguments["max_results"] = min(
                        arguments.get("max_results", MAX_PAPERS_FOR_MODEL),
                        MAX_PAPERS_FOR_MODEL,
                    )
                    if SHOW_TOOL_TRACE:
                        print(
                            f"Model requested tool: {function['name']}({arguments})"
                        )
                    result = await session.call_tool(
                        function["name"],
                        arguments=arguments,
                    )
                    raw_tool_result = result.content[0].text
                    retrieved_papers = json.loads(raw_tool_result)["papers"]
                    if SHOW_TOOL_TRACE:
                        paper_count = len(retrieved_papers)
                        print(f"MCP tool returned {paper_count} papers.")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": function["name"],
                            "content": compact_tool_result(raw_tool_result),
                        }
                    )

    raise RuntimeError("The model requested too many tool calls. Please try again.")


async def save_to_notion(title: str, content: str) -> dict:
    """Create a Notion research page by calling the Notion MCP tool."""
    async with stdio_client(NOTION_SERVER_PARAMETERS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "create_research_page",
                arguments={"title": title, "content": content},
            )

            if getattr(result, "isError", False):
                raise RuntimeError(result.content[0].text)

            return json.loads(result.content[0].text)


def report_path_for_topic(topic: str) -> Path:
    """Create a filesystem-safe report name from the research topic."""
    safe_topic = re.sub(r"[^A-Za-z0-9]+", "_", topic).strip("_")
    return Path(f"{safe_topic or 'research'}_report.md")


def add_sources_section(report: str, papers: list[dict]) -> str:
    """Append an exact, complete bibliography from the retrieved paper data."""
    report_body = re.split(r"\n## Sources\s*", report, maxsplit=1, flags=re.IGNORECASE)[0]
    source_lines = [report_body.rstrip(), "", "## Sources", ""]

    for number, paper in enumerate(papers, start=1):
        authors = ", ".join(paper["authors"]) or "Unknown authors"
        source_lines.append(
            f"[{number}] {paper['title']}, {authors}, {paper['year']}, "
            f"{paper['source']}, {paper['url']}"
        )

    return "\n".join(source_lines) + "\n"


def save_report(topic: str, report: str) -> Path:
    """Save the generated Markdown report beside the application files."""
    report_path = report_path_for_topic(topic)
    report_path.write_text(report, encoding="utf-8")
    return report_path


def find_runtime_error(error: BaseException) -> RuntimeError | None:
    """Find an application error nested inside an async exception group."""
    if isinstance(error, RuntimeError):
        return error

    if isinstance(error, BaseExceptionGroup):
        for nested_error in error.exceptions:
            runtime_error = find_runtime_error(nested_error)
            if runtime_error:
                return runtime_error

    return None


def main() -> None:
    question = input("What would you like to research?\n> ").strip()

    if not question:
        print("Please enter a research question.")
        return

    print("\nSearching for papers and generating a report...\n")

    try:
        report, papers = asyncio.run(research(question))
    except RuntimeError as error:
        print(f"Error: {error}")
        return
    except BaseExceptionGroup as error:
        runtime_error = find_runtime_error(error)
        if runtime_error:
            print(f"Error: {runtime_error}")
            return
        raise

    try:
        complete_report = add_sources_section(report, papers)
        report_path = save_report(question, complete_report)
    except OSError as error:
        print(f"Error: Could not save the report: {error}")
        return

    try:
        notion_page = asyncio.run(
            save_to_notion(f"{question} Research Report", complete_report)
        )
    except RuntimeError as error:
        print(complete_report)
        print(f"\nReport saved locally to {report_path.resolve()}")
        print(f"Error: Could not save the report to Notion: {error}")
        return
    except BaseExceptionGroup as error:
        runtime_error = find_runtime_error(error)
        if runtime_error:
            print(complete_report)
            print(f"\nReport saved locally to {report_path.resolve()}")
            print(f"Error: Could not save the report to Notion: {runtime_error}")
            return
        raise

    print(complete_report)
    print(f"\nReport saved to {report_path.resolve()}")
    print(f"Notion page created: {notion_page['url']}")


if __name__ == "__main__":
    main()
