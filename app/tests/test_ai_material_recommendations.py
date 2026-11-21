import asyncio
import sys
from types import ModuleType, SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.ai_provider import router
from app.modules.ai_provider.models import SearchQueries


def test_resource_search_clients_have_bounded_http_timeouts(monkeypatch):
    from app.modules.ai_provider.services import services

    observed_timeouts = {}
    monkeypatch.setattr(services, "_required_setting", lambda _name: "test-key")

    async def run_inline(operation):
        return operation()

    monkeypatch.setattr(services, "_run_blocking", run_inline)

    semantic_module = ModuleType("semanticscholar")

    class SemanticScholar:
        def __init__(self, *, timeout, api_key, retry):
            assert api_key == "test-key"
            assert retry is False
            observed_timeouts["semantic"] = timeout

        def search_paper(self, *, query):
            return SimpleNamespace(raw_data={"query": query})

    setattr(semantic_module, "SemanticScholar", SemanticScholar)
    monkeypatch.setitem(sys.modules, "semanticscholar", semantic_module)
    asyncio.run(services.get_papers("paper query"))

    tavily_module = ModuleType("tavily")

    class TavilyClient:
        def __init__(self, api_key):
            assert api_key == "test-key"

        def search(self, **kwargs):
            observed_timeouts["tavily"] = kwargs["timeout"]
            return {"results": []}

    setattr(tavily_module, "TavilyClient", TavilyClient)
    monkeypatch.setitem(sys.modules, "tavily", tavily_module)
    asyncio.run(services.get_search_results("web query"))

    discovery_module = ModuleType("googleapiclient.discovery")

    class GoogleSearch:
        def list(self, **_kwargs):
            return self

        def execute(self):
            return {"items": []}

    class GoogleClient:
        def search(self):
            return GoogleSearch()

        def volumes(self):
            return GoogleSearch()

    def build(service_name, version, *, developerKey, http):
        assert version in {"v1", "v3"}
        assert developerKey == "test-key"
        observed_timeouts[service_name] = http.timeout
        return GoogleClient()

    setattr(discovery_module, "build", build)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery_module)
    asyncio.run(services.get_videos("video query"))
    asyncio.run(services.get_books("book query"))

    expected_timeout = services.RESOURCE_SEARCH_HTTP_TIMEOUT_SECONDS
    assert observed_timeouts == {
        "semantic": expected_timeout,
        "tavily": expected_timeout,
        "youtube": expected_timeout,
        "books": expected_timeout,
    }


def test_get_materials_passes_validated_response_language(monkeypatch):
    observed = {}

    class Database:
        def scalar(self, _query):
            return "Spanish"

    class Provider:
        def __init__(self, *, db, user_token):
            assert db is database
            assert user_token == "token"

        async def call_ai(
            self,
            *,
            agent_id,
            user_prompt,
            response_language,
        ):
            observed.update(
                agent_id=agent_id,
                user_prompt=user_prompt,
                response_language=response_language,
            )
            return SearchQueries(
                paper_query="paper",
                search_query="web",
                yt_videos_query="video",
                books_query="book",
            )

    database = Database()
    monkeypatch.setattr(router, "AiProvider", Provider)

    result = asyncio.run(
        router.get_materials(
            user_prompt="recommend materials",
            agent_id=uuid4(),
            response_language="spanish",
            include_videos=False,
            include_books=False,
            include_papers=False,
            include_web=False,
            token="token",
            db=database,
        )
    )

    assert observed["response_language"] == "Spanish"
    assert observed["user_prompt"] == "recommend materials"
    assert result == ([], [], [], [])


def test_get_materials_runs_external_searches_concurrently(monkeypatch):
    started = set()
    all_started = asyncio.Event()

    class Database:
        def scalar(self, _query):
            return None

    class Provider:
        def __init__(self, **_kwargs):
            pass

        async def call_ai(self, **_kwargs):
            return SearchQueries(
                paper_query="paper",
                search_query="web",
                yt_videos_query="video",
                books_query="book",
            )

    async def wait_for_all(name, value):
        started.add(name)
        if len(started) == 4:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=0.5)
        return value

    monkeypatch.setattr(router, "AiProvider", Provider)
    monkeypatch.setattr(
        router, "get_papers", lambda _query: wait_for_all("paper", {"paper": True})
    )
    monkeypatch.setattr(
        router, "get_videos", lambda _query: wait_for_all("video", [{"video": True}])
    )
    monkeypatch.setattr(
        router, "get_books", lambda _query: wait_for_all("book", [{"book": True}])
    )
    monkeypatch.setattr(
        router,
        "get_search_results",
        lambda _query: wait_for_all("web", {"web": True}),
    )

    result = asyncio.run(
        router.get_materials(
            user_prompt="recommend materials",
            agent_id=uuid4(),
            response_language=None,
            token="token",
            db=cast(Session, Database()),
        )
    )

    assert started == {"paper", "video", "book", "web"}
    assert result == (
        {"paper": True},
        [{"video": True}],
        [{"book": True}],
        {"web": True},
    )


def test_get_materials_rejects_unsupported_response_language(monkeypatch):
    class Database:
        def scalar(self, _query):
            return None

    class UnexpectedProvider:
        def __init__(self, **_kwargs):
            pytest.fail("AI provider should not be called for an invalid language")

    monkeypatch.setattr(router, "AiProvider", UnexpectedProvider)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            router.get_materials(
                user_prompt="recommend materials",
                agent_id=uuid4(),
                response_language="unsupported",
                token="token",
                db=Database(),
            )
        )

    assert error.value.status_code == 422
