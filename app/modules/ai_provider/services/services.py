"""Clients for external academic, web, video, and book search providers."""

import asyncio
import os
from pathlib import Path
from typing import Any, Callable, Coroutine, TypeVar

from dotenv import load_dotenv

_T = TypeVar("_T")
_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / ".env.api_utils"
load_dotenv(dotenv_path=_CONFIG_PATH)


def _required_setting(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name} is not configured. Add it to {_CONFIG_PATH.name}."
        )
    return value


def _run_blocking(operation: Callable[[], _T]) -> Coroutine[Any, Any, _T]:
    return asyncio.to_thread(operation)


async def get_papers(query: str) -> dict[str, Any]:
    """Search Semantic Scholar and return its raw response data."""
    if not query.strip():
        raise ValueError("The paper search query cannot be empty.")

    api_key = _required_setting("SS_API")

    def search() -> dict[str, Any]:
        try:
            from semanticscholar import SemanticScholar
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Semantic Scholar support is unavailable. Install semanticscholar."
            ) from exc

        client = SemanticScholar(api_key=api_key)
        result = client.search_paper(query=query.strip())
        return result.raw_data

    return await _run_blocking(search)


async def get_videos(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search YouTube videos matching a query."""
    if not query.strip():
        raise ValueError("The video search query cannot be empty.")
    if not 1 <= max_results <= 50:
        raise ValueError("max_results must be between 1 and 50.")

    api_key = _required_setting("YT_API")

    def search() -> list[dict[str, Any]]:
        try:
            from googleapiclient.discovery import build
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "YouTube support is unavailable. Install google-api-python-client."
            ) from exc

        youtube = build("youtube", "v3", developerKey=api_key)
        response = (
            youtube.search()
            .list(
                part="snippet",
                q=query.strip(),
                type="video",
                maxResults=max_results,
            )
            .execute()
        )
        return response.get("items", [])

    return await _run_blocking(search)


async def get_search_results(query: str) -> dict[str, Any]:
    """Search the web with Tavily."""
    if not query.strip():
        raise ValueError("The web search query cannot be empty.")

    api_key = _required_setting("TAVILY_API_KEY")

    def search() -> dict[str, Any]:
        try:
            from tavily import TavilyClient
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Tavily support is unavailable. Install tavily-python."
            ) from exc

        client = TavilyClient(api_key)
        return client.search(
            query=query.strip(),
            search_depth="advanced",
            max_results=15,
            include_usage=True,
        )

    return await _run_blocking(search)


async def get_books(query: str) -> list[dict[str, Any]]:
    """Search Google Books volumes matching a query."""
    if not query.strip():
        raise ValueError("The book search query cannot be empty.")

    api_key = _required_setting("BOOKS_API")

    def search() -> list[dict[str, Any]]:
        try:
            from googleapiclient.discovery import build
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Google Books support is unavailable. Install google-api-python-client."
            ) from exc

        books = build("books", "v1", developerKey=api_key)
        response = books.volumes().list(q=query.strip(), maxResults=15).execute()
        return response.get("items", [])

    return await _run_blocking(search)


# Backward-compatible aliases for existing route imports.
getPapers = get_papers
getVideos = get_videos
getSearchResuls = get_search_results
getBooks = get_books
