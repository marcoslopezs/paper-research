"""MCP server that creates research-report pages in Notion."""

import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP


NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2026-03-11"

mcp = FastMCP("Notion Research Reports")


def load_local_env() -> None:
    """Load simple KEY=value settings from .env without printing their values."""
    env_path = Path(".env")
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", maxsplit=1)
        os.environ.setdefault(key.strip(), value.strip())


def strip_inline_markdown(text: str) -> str:
    """Keep text readable when converting simple Markdown to Notion blocks."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return re.sub(r"\[(.+?)\]\((.+?)\)", r"\1: \2", text)


def text_block(block_type: str, text: str) -> dict:
    """Build a Notion text block for a paragraph, heading, or bullet."""
    return {
        "object": "block",
        "type": block_type,
        block_type: {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": strip_inline_markdown(text)[:2000]},
                }
            ]
        },
    }


def markdown_to_blocks(content: str) -> list[dict]:
    """Convert the report's simple Markdown structure into Notion blocks."""
    blocks = []

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("# "):
            continue
        if line.startswith("## "):
            blocks.append(text_block("heading_2", line[3:]))
        elif line.startswith("### "):
            blocks.append(text_block("heading_3", line[4:]))
        elif line.startswith("- "):
            blocks.append(text_block("bulleted_list_item", line[2:]))
        else:
            blocks.append(text_block("paragraph", line))

    return blocks


def create_notion_page(title: str, content: str) -> dict:
    """Create a Notion child page containing the generated report."""
    load_local_env()
    token = os.getenv("NOTION_TOKEN")
    parent_page_id = os.getenv("NOTION_PARENT_PAGE_ID")

    if not token:
        raise RuntimeError("NOTION_TOKEN is missing. Add it to your .env file.")
    if not parent_page_id:
        raise RuntimeError(
            "NOTION_PARENT_PAGE_ID is missing. Add it to your .env file."
        )

    blocks = markdown_to_blocks(content)
    if not blocks:
        raise RuntimeError("The report has no content to save to Notion.")

    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title[:2000]}}]
            }
        },
        "children": blocks[:100],
    }
    request = Request(
        NOTION_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Notion returned HTTP {error.code}: {details}") from error
    except URLError as error:
        raise RuntimeError("Could not reach Notion. Check your internet connection.") from error
    except TimeoutError as error:
        raise RuntimeError("Notion took too long to respond. Please try again.") from error


@mcp.tool()
def create_research_page(title: str, content: str) -> dict:
    """Create a Notion page under the configured research-report parent page."""
    page = create_notion_page(title, content)
    return {"page_id": page["id"], "url": page["url"]}


if __name__ == "__main__":
    mcp.run(transport="stdio")
