"""Search arXiv for papers about a topic."""

import json
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ARXIV_API_URL = "https://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_TIMEOUT = 5
ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}


def search_arxiv(query: str, max_results: int = 5) -> list[dict]:
    """Return basic metadata for arXiv papers matching a search query."""
    search_terms = query.replace('"', "").split()
    arxiv_query = " AND ".join(f"all:{term}" for term in search_terms)
    parameters = {
        "search_query": arxiv_query,
        "start": 0,
        "max_results": max_results,
    }
    request_url = f"{ARXIV_API_URL}?{urlencode(parameters)}"

    headers = {"User-Agent": "paper-research-agent/0.1"}

    try:
        request = Request(request_url, headers=headers)
        with urlopen(request, timeout=30) as response:
            root = ET.fromstring(response.read())
    except HTTPError as error:
        raise RuntimeError(f"The arXiv API returned HTTP {error.code}.") from error
    except URLError as error:
        raise RuntimeError("Could not reach arXiv. Check your internet connection.") from error
    except TimeoutError as error:
        raise RuntimeError("arXiv took too long to respond. Please try again shortly.") from error
    except ET.ParseError as error:
        raise RuntimeError("arXiv returned an unreadable response. Please try again.") from error

    papers = []
    for entry in root.findall("atom:entry", ATOM_NAMESPACE):
        title = " ".join(entry.findtext("atom:title", "", ATOM_NAMESPACE).split())
        abstract = " ".join(entry.findtext("atom:summary", "", ATOM_NAMESPACE).split())
        published = entry.findtext("atom:published", "", ATOM_NAMESPACE)
        authors = [
            author.findtext("atom:name", "Unknown author", ATOM_NAMESPACE)
            for author in entry.findall("atom:author", ATOM_NAMESPACE)
        ]

        papers.append(
            {
                "title": title or "Untitled paper",
                "authors": authors,
                "year": published[:4] or "Unknown year",
                "abstract": abstract or "No abstract available.",
                "url": entry.findtext("atom:id", "No URL available.", ATOM_NAMESPACE),
                "source": "arXiv",
            }
        )

    return papers


def search_semantic_scholar(query: str, max_results: int = 5) -> list[dict]:
    """Return basic metadata for Semantic Scholar papers matching a query."""
    parameters = {
        "query": query,
        "limit": max_results,
        "fields": "title,authors,year,abstract,url",
    }
    request_url = f"{SEMANTIC_SCHOLAR_API_URL}?{urlencode(parameters)}"

    try:
        request = Request(request_url, headers={"User-Agent": "paper-research-agent/0.1"})
        with urlopen(request, timeout=SEMANTIC_SCHOLAR_TIMEOUT) as response:
            data = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Semantic Scholar returned HTTP {error.code}.") from error
    except URLError as error:
        raise RuntimeError("Could not reach Semantic Scholar.") from error
    except TimeoutError as error:
        raise RuntimeError("Semantic Scholar took too long to respond.") from error

    papers = []
    for item in data.get("data", []):
        papers.append(
            {
                "title": item.get("title") or "Untitled paper",
                "authors": [author["name"] for author in item.get("authors", [])],
                "year": item.get("year") or "Unknown year",
                "abstract": item.get("abstract") or "No abstract available.",
                "url": item.get("url") or "No URL available.",
                "source": "Semantic Scholar",
            }
        )

    return papers


def deduplicate_papers(papers: list[dict]) -> list[dict]:
    """Keep the first paper for each title, ignoring punctuation and letter case."""
    unique_papers = []
    seen_titles = set()

    for paper in papers:
        title_key = "".join(character for character in paper["title"].lower() if character.isalnum())
        if title_key not in seen_titles:
            unique_papers.append(paper)
            seen_titles.add(title_key)

    return unique_papers


def search_all_papers(query: str, max_results: int = 7) -> tuple[list[dict], list[str]]:
    """Search both sources, keeping arXiv results if Semantic Scholar is unavailable."""
    papers = search_arxiv(query, max_results)
    warnings = []

    try:
        papers.extend(search_semantic_scholar(query, max_results))
    except RuntimeError as error:
        warnings.append(str(error))

    return deduplicate_papers(papers), warnings


def print_papers(papers: list[dict]) -> None:
    """Print papers in a simple, readable terminal format."""
    if not papers:
        print("No papers found. Try a broader or different topic.")
        return

    for number, paper in enumerate(papers, start=1):
        authors = ", ".join(paper["authors"]) or "Unknown authors"
        print(f"\n{number}. {paper['title']}")
        print(f"   Authors: {authors}")
        print(f"   Year: {paper['year']}")
        print(f"   Source: {paper['source']}")
        print(f"   URL: {paper['url']}")


def main() -> None:
    topic = input("What topic do you want to research?\n> ").strip()

    if not topic:
        print("Please enter a research topic.")
        return

    print("\nSearching for relevant papers...")

    try:
        papers, warnings = search_all_papers(topic)
    except RuntimeError as error:
        print(f"Error: {error}")
        return

    print_papers(papers)

    for warning in warnings:
        print(f"\nWarning: {warning} Continuing with the available source.")


if __name__ == "__main__":
    main()
