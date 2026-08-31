# Paper Research Agent

A small Python project I built to learn how an AI agent can use tools through the Model Context Protocol (MCP).

The agent searches academic papers, creates a research report from the retrieved abstracts, saves the report locally, and creates a page in Notion.

## What it does

1. The user enters a research topic in the terminal.
2. A local Ollama model decides to use the paper-search tool.
3. The Paper MCP server searches arXiv and Semantic Scholar.
4. The model generates a structured Markdown report from the retrieved paper metadata and abstracts.
5. The report is saved locally as `<topic>_report.md`.
6. The Notion MCP server creates a new Notion page with the report.

## Architecture

```text
User
  |
  v
agent.py + local Ollama model
  |
  +--> Paper MCP server --> arXiv + Semantic Scholar
  |
  +--> Notion MCP server --> Notion API
```

## Project files

```text
agent.py              Main application and agent loop
main.py               Direct academic paper search functions
paper_server.py       MCP server for paper search
notion_server.py      MCP server for creating Notion pages
test_mcp.py           Test client for the paper MCP server
test_notion_mcp.py    Test client for the Notion MCP server
```

## Requirements

- Python 3.11 or later
- [Ollama](https://ollama.com/)
- A Notion internal integration and a parent page shared with it

Install the Python dependency:

```bash
python -m pip install -r requirements.txt
```

If you use `uv` instead of `pip`:

```bash
uv pip install -r requirements.txt
```

Download the local model if needed:

```bash
ollama pull gemma4:e2b
```

## Notion setup

Create a `.env` file in the project root:

```env
NOTION_TOKEN=your_notion_internal_integration_secret
NOTION_PARENT_PAGE_ID=your_parent_page_id
```

The parent page must be shared with the Notion integration. See `.env.example` for the required variable names.

Never commit the `.env` file.

## Usage

Run the agent:

```bash
python agent.py
```

Example:

```text
What would you like to research?
> Stellarators
```

The application creates a local file such as `Stellarators_report.md` and prints the URL of the new Notion page.

## How MCP is used

This project has two custom MCP servers:

- `paper_server.py` exposes `search_papers(query, max_results)`.
- `notion_server.py` exposes `create_research_page(title, content)`.

`agent.py` acts as the MCP client. It discovers and calls these tools through local stdio connections.

## Limitations

- Reports are based on paper metadata and abstracts, not full paper text.
- The quality and speed of the report depend on the local Ollama model and available hardware.
- Semantic Scholar may rate-limit public requests; arXiv remains available as the fallback source.
- The Markdown-to-Notion conversion supports headings, paragraphs, and bullet lists.
