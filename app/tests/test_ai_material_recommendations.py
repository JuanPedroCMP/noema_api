import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.ai_provider import router
from app.modules.ai_provider.models import SearchQueries


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
