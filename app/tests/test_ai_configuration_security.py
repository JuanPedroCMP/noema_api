import asyncio
import socket
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core import admin
from app.core.ai_endpoint import validate_ai_endpoint


def _current_user_stub(user):
    def get_current_user(token, db):
        assert token == "token"
        assert db is not None
        return user

    return get_current_user


def test_admin_access_requires_configured_single_email(monkeypatch):
    user = SimpleNamespace(primary_email="owner@example.com")
    monkeypatch.setattr(admin, "get_current_user", _current_user_stub(user))
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)

    with pytest.raises(HTTPException) as error:
        admin.require_admin(token="token", db=object())

    assert error.value.status_code == 503


def test_admin_access_matches_configured_email_case_insensitively(monkeypatch):
    user = SimpleNamespace(primary_email="Owner@Example.com")
    monkeypatch.setattr(admin, "get_current_user", _current_user_stub(user))
    monkeypatch.setenv("ADMIN_EMAIL", " owner@example.com ")

    assert admin.require_admin(token="token", db=object()) is user


def test_other_users_are_not_administrators(monkeypatch):
    user = SimpleNamespace(primary_email="other@example.com")
    monkeypatch.setattr(admin, "get_current_user", _current_user_stub(user))
    monkeypatch.setenv("ADMIN_EMAIL", "owner@example.com")

    with pytest.raises(HTTPException) as error:
        admin.require_admin(token="token", db=object())

    assert error.value.status_code == 403


def test_custom_provider_urls_require_https_or_explicit_local_mode(monkeypatch):
    monkeypatch.delenv("AI_ALLOW_LOCAL_AI", raising=False)
    validate_ai_endpoint("https://8.8.8.8/v1")

    with pytest.raises(HTTPException) as error:
        validate_ai_endpoint("http://localhost:11434/v1")
    assert error.value.status_code == 422

    monkeypatch.setenv("AI_ALLOW_LOCAL_AI", "true")
    validate_ai_endpoint("http://localhost:11434/v1")
    validate_ai_endpoint("http://192.168.1.50:11434/v1")


def test_global_catalog_mutations_are_admin_only():
    from app.main import app

    protected_routes = {
        "/api/v1/ai/provider/create": "post",
        "/api/v1/ai/provider/update/{identificator}": "put",
        "/api/v1/ai/provider/delete/{identificator}": "delete",
        "/api/v1/ai/ai_model/create": "post",
        "/api/v1/ai/ai_model/update/{identificator}": "put",
        "/api/v1/ai/ai_model/delete/{identificator}": "delete",
        "/api/v1/ai/shared_api_key/list": "get",
        "/api/v1/ai/shared_api_key/create": "post",
        "/api/v1/ai/shared_api_key/update/{identificator}": "put",
        "/api/v1/ai/shared_api_key/delete/{identificator}": "delete",
        "/api/v1/ai/agent/create": "post",
        "/api/v1/ai/agent/update/{identificator}": "put",
        "/api/v1/ai/agent/delete/{identificator}": "delete",
        "/api/v1/ai/agent_model/create": "post",
        "/api/v1/ai/agent_model/update/{identificator}": "put",
        "/api/v1/ai/agent_model/delete/{identificator}": "delete",
    }

    paths = app.openapi()["paths"]
    for path, method in protected_routes.items():
        assert "security" in paths[path][method]


def test_global_catalog_reads_remain_public():
    from app.main import app

    public_routes = {
        "/api/v1/ai/provider/get/{identificator}",
        "/api/v1/ai/provider/list",
        "/api/v1/ai/ai_model/get/{identificator}",
        "/api/v1/ai/ai_model/list",
        "/api/v1/ai/agent/get/{identificator}",
        "/api/v1/ai/agent/list",
        "/api/v1/ai/agent_model/get/{identificator}",
        "/api/v1/ai/agent_model/list",
    }

    paths = app.openapi()["paths"]
    for path in public_routes:
        assert "security" not in paths[path]["get"]


def test_personal_ai_configuration_requires_authentication():
    from app.main import app

    paths = app.openapi()["paths"]
    for path in (
        "/api/v1/ai/me/providers",
        "/api/v1/ai/me/providers/{provider_id}",
        "/api/v1/ai/me/models",
        "/api/v1/ai/me/models/{model_id}",
        "/api/v1/ai/me/agents",
        "/api/v1/ai/me/agents/{agent_id}",
        "/api/v1/ai/me/agent-models",
        "/api/v1/ai/me/agent-models/{link_id}",
        "/api/v1/ai/user_api_key/delete/{identificator}",
    ):
        for operation in paths[path].values():
            assert "security" in operation


def test_delete_user_api_key_removes_key_and_model_links(monkeypatch):
    from app.core.db_models.ai_models import UserApiKeyCanUseIaModel
    from app.modules.ai import services

    user = SimpleNamespace(id=uuid4())
    api_key = SimpleNamespace(id=uuid4(), id_user=user.id, is_active=True)
    monkeypatch.setattr(services, "get_current_user", lambda _token, _db: user)

    class Db:
        def __init__(self):
            self.deleted = []
            self.executed = []
            self.commits = 0

        def scalar(self, statement):
            assert user.id in statement.compile().params.values()
            return api_key

        def execute(self, statement):
            self.executed.append(statement)

        def delete(self, value):
            self.deleted.append(value)

        def commit(self):
            self.commits += 1

    db = Db()

    assert services.delete_user_api_key("token", str(api_key.id), cast(Session, db))
    assert len(db.executed) == 1
    assert str(db.executed[0].table) == str(UserApiKeyCanUseIaModel.__table__)
    assert db.deleted == [api_key]
    assert db.commits == 1
    assert api_key.is_active is True


def test_delete_user_api_key_cannot_delete_another_users_key(monkeypatch):
    from app.modules.ai import services

    user = SimpleNamespace(id=uuid4())
    other_users_key = SimpleNamespace(id=uuid4(), id_user=uuid4())
    monkeypatch.setattr(services, "get_current_user", lambda _token, _db: user)

    class Db:
        def scalar(self, statement):
            assert user.id in statement.compile().params.values()

    with pytest.raises(HTTPException) as error:
        services.delete_user_api_key(
            "token", str(other_users_key.id), cast(Session, Db())
        )

    assert error.value.status_code == 404


def test_provider_hostname_cannot_resolve_to_internal_network(monkeypatch):
    def resolve_internal(host, port, family=0, type=0, proto=0, flags=0):
        assert host == "provider.test"
        assert port == 443
        assert family == 0
        assert type == socket.SOCK_STREAM
        assert proto == 0
        assert flags == 0
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", resolve_internal)

    with pytest.raises(HTTPException) as error:
        validate_ai_endpoint("https://provider.test/v1")
    assert error.value.status_code == 422


def test_provider_urls_reject_private_ip_without_local_mode(monkeypatch):
    monkeypatch.delenv("AI_ALLOW_LOCAL_AI", raising=False)

    with pytest.raises(HTTPException) as error:
        validate_ai_endpoint("https://10.0.0.8/v1")
    assert error.value.status_code == 422


def test_personal_agent_models_are_included_in_model_selection():
    from uuid import uuid4

    from app.modules.ai.models import AgentModelFilters
    from app.modules.ai.services import list_agent_models

    class QueryCapture:
        statement = None

        def scalars(self, statement):
            self.statement = statement
            return SimpleNamespace(all=lambda: [])

    db = QueryCapture()
    list_agent_models(
        filters=AgentModelFilters(id_agent=uuid4()),
        db=db,
        owner_id=uuid4(),
    )

    sql = str(db.statement)
    assert "ai.agent.id_user IS NULL OR ai.agent.id_user =" in sql
    assert "ai.ai_provider.id_user IS NULL OR ai.ai_provider.id_user =" in sql


def test_personal_key_model_lookup_is_always_user_scoped(monkeypatch):
    from uuid import uuid4

    from app.modules.ai import services

    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(services, "get_current_user", lambda _token, _db: user)

    class QueryCapture:
        statement = None

        def scalar(self, statement):
            self.statement = statement
            return SimpleNamespace(id=uuid4())

    db = QueryCapture()
    services.get_user_api_key_can_use_ia_model(str(uuid4()), db, "token")

    sql = str(db.statement)
    assert "ai.user_api_key.id_user =" in sql
    assert "AND (ai.user_api_key_can_use_ia_model.id =" in sql


def test_model_api_keys_are_loaded_in_two_user_scoped_queries():
    from app.core.db_models.ai_models import AgentModel, AiModel
    from app.modules.ai_provider.services.ai_compatibility_layer import AiProvider

    owner_id = uuid4()
    model_ids = [uuid4(), uuid4(), uuid4()]
    personal_key = object()
    shared_key = object()

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class Db:
        def __init__(self):
            self.statements = []

        def execute(self, statement):
            self.statements.append(statement)
            if len(self.statements) == 1:
                return Result([(model_ids[0], personal_key)])
            return Result([(model_ids[1], shared_key)])

    db = Db()
    preference_order = [
        (
            cast(AiModel, SimpleNamespace(id=model_id)),
            1.0,
            cast(AgentModel, object()),
        )
        for model_id in model_ids
    ]
    personal, shared = AiProvider(cast(Session, db), "token")._load_model_api_keys(
        owner_id,
        preference_order,
    )

    assert len(db.statements) == 2
    assert personal == {model_ids[0]: [personal_key]}
    assert shared == {model_ids[1]: [shared_key]}
    assert owner_id in db.statements[0].compile().params.values()
    assert "ai.user_api_key.is_active IS true" in str(db.statements[0])


def test_ai_generation_skips_models_without_active_api_keys(monkeypatch):
    from app.modules.ai_provider.services import ai_compatibility_layer

    user = SimpleNamespace(id=uuid4())
    agent_id = uuid4()
    agent = SimpleNamespace(
        id=agent_id,
        task="create_flashcard",
        base_system_prompt="system",
        temperature=0.3,
    )
    model_without_key = SimpleNamespace(
        id=uuid4(), id_ai_provider=uuid4(), display_name="No key", is_active=True
    )
    model_with_key = SimpleNamespace(
        id=uuid4(), id_ai_provider=uuid4(), display_name="Has key", is_active=True
    )
    model_with_shared_key = SimpleNamespace(
        id=uuid4(),
        id_ai_provider=uuid4(),
        display_name="Shared key only",
        is_active=True,
    )
    agent_model_without_key = SimpleNamespace(
        custom_system_prompt=None, custom_temperature=None
    )
    agent_model_with_key = SimpleNamespace(
        custom_system_prompt=None, custom_temperature=None
    )
    agent_model_with_shared_key = SimpleNamespace(
        custom_system_prompt=None, custom_temperature=None
    )
    personal_key = object()
    shared_key = object()

    class Db:
        def __init__(self):
            self.commits = 0

        def scalar(self, _statement):
            return agent

        def commit(self):
            self.commits += 1

        def rollback(self):
            pass

    db = Db()
    monkeypatch.setattr(
        ai_compatibility_layer, "get_current_user", lambda **_kwargs: user
    )
    monkeypatch.setattr(
        ai_compatibility_layer.AiProvider,
        "_get_response_model",
        staticmethod(lambda _task: object()),
    )
    monkeypatch.setattr(
        ai_compatibility_layer.AiProvider,
        "_calculate_preference_order",
        lambda _self, _agent_id, _owner_id: [
            (model_without_key, 2.0, agent_model_without_key),
            (model_with_shared_key, 1.5, agent_model_with_shared_key),
            (model_with_key, 1.0, agent_model_with_key),
        ],
    )
    monkeypatch.setattr(
        ai_compatibility_layer.AiProvider,
        "_load_model_api_keys",
        lambda _self, _owner_id, _preference_order: (
            {model_with_key.id: [personal_key]},
            {model_with_shared_key.id: [shared_key]},
        ),
    )
    monkeypatch.setattr(
        ai_compatibility_layer.AiProvider,
        "_get_response_language",
        lambda _self, _user_id: "Portuguese",
    )

    provider_lookups = []

    def get_provider(**kwargs):
        provider_lookups.append(kwargs["identificator"])
        return SimpleNamespace(is_active=True)

    monkeypatch.setattr(ai_compatibility_layer, "get_provider", get_provider)

    invoked_models = []
    invoked_keys = []
    invoked_prompts = []

    async def invoke_model(
        _self, model, _api_keys, _provider, _system_prompt, _temperature,
        _user_prompt, _response_model,
    ):
        assert db.commits >= 2
        invoked_models.append(model)
        invoked_keys.append(_api_keys)
        invoked_prompts.append(_system_prompt)
        if personal_key in _api_keys:
            raise RuntimeError("Personal API key failed.")
        return "response", object()

    monkeypatch.setattr(
        ai_compatibility_layer.AiProvider, "_invoke_model", invoke_model
    )
    monkeypatch.setattr(
        ai_compatibility_layer.AiProvider, "_record_usage", lambda *_args: None
    )

    result = asyncio.run(
        ai_compatibility_layer.AiProvider(db, "token").call_ai("prompt", agent_id)
    )

    assert result == "response"
    assert provider_lookups == [str(model_with_shared_key.id_ai_provider)]
    assert invoked_models == [model_with_shared_key]
    assert invoked_keys == [[shared_key]]
    assert all("Respond in Portuguese." in prompt for prompt in invoked_prompts)


def test_ai_generation_tries_same_model_shared_key_before_fallback_model(monkeypatch):
    from app.modules.ai_provider.services import ai_compatibility_layer

    user_id = uuid4()
    agent_id = uuid4()
    preferred_model = SimpleNamespace(
        id=uuid4(), display_name="Preferred model", id_ai_provider=uuid4()
    )
    fallback_model = SimpleNamespace(
        id=uuid4(), display_name="Fallback model", id_ai_provider=uuid4()
    )
    personal_key = object()
    same_provider_shared_key = object()
    fallback_key = object()
    context = (
        user_id,
        SimpleNamespace(id=agent_id),
        object(),
        [
            (preferred_model, 2.0, object()),
            (fallback_model, 1.0, object()),
        ],
        None,
        {
            preferred_model.id: [personal_key],
            fallback_model.id: [fallback_key],
        },
        {preferred_model.id: [same_provider_shared_key]},
    )
    provider = ai_compatibility_layer.AiProvider(cast(Session, object()), "token")
    monkeypatch.setattr(provider, "_prepare_call_context", lambda *_args: context)
    monkeypatch.setattr(
        provider,
        "_prepare_model_attempt",
        lambda _model, _agent, _agent_model, _owner_id, api_keys: (
            api_keys,
            SimpleNamespace(is_active=True),
            "system",
            0.3,
        ),
    )
    attempted_models = []
    attempted_keys = []

    async def invoke_model(model, api_keys, *_args):
        attempted_models.append(model)
        attempted_keys.append(api_keys)
        if model is preferred_model:
            raise RuntimeError("Both keys for the preferred model failed.")
        return "fallback response", object()

    monkeypatch.setattr(provider, "_invoke_model", invoke_model)
    monkeypatch.setattr(provider, "_record_usage", lambda *_args: None)

    result = asyncio.run(provider.call_ai("prompt", agent_id))

    assert result == "fallback response"
    assert attempted_models == [preferred_model, fallback_model]
    assert attempted_keys == [
        [personal_key, same_provider_shared_key],
        [fallback_key],
    ]


def test_ai_generation_fails_fast_without_any_active_api_keys(monkeypatch):
    from app.modules.ai_provider.services import ai_compatibility_layer

    user_id = uuid4()
    agent_id = uuid4()
    model = SimpleNamespace(
        id=uuid4(), display_name="No key", id_ai_provider=uuid4()
    )
    agent = SimpleNamespace(id=agent_id)
    context = (
        user_id,
        agent,
        object(),
        [(model, 1.0, object())],
        None,
        {},
        {},
    )
    provider = ai_compatibility_layer.AiProvider(cast(Session, object()), "token")
    monkeypatch.setattr(
        provider, "_prepare_call_context", lambda *_args: context
    )
    invoked = False

    async def invoke_model(*_args):
        nonlocal invoked
        invoked = True

    monkeypatch.setattr(provider, "_invoke_model", invoke_model)

    with pytest.raises(HTTPException) as error:
        asyncio.run(provider.call_ai("prompt", agent_id))

    assert error.value.status_code == 422
    assert "No active API keys" in error.value.detail
    assert not invoked


def test_ai_generation_keeps_fallback_available_after_a_model_timeout(monkeypatch):
    from app.modules.ai_provider.services import ai_compatibility_layer

    user_id = uuid4()
    agent_id = uuid4()
    slow_model = SimpleNamespace(
        id=uuid4(), display_name="Slow model", id_ai_provider=uuid4()
    )
    fallback_model = SimpleNamespace(
        id=uuid4(), display_name="Fallback model", id_ai_provider=uuid4()
    )
    slow_key = object()
    fallback_key = object()
    context = (
        user_id,
        SimpleNamespace(id=agent_id),
        object(),
        [
            (slow_model, 2.0, object()),
            (fallback_model, 1.0, object()),
        ],
        None,
        {
            slow_model.id: [slow_key],
            fallback_model.id: [fallback_key],
        },
        {},
    )
    provider = ai_compatibility_layer.AiProvider(cast(Session, object()), "token")
    monkeypatch.setattr(provider, "_prepare_call_context", lambda *_args: context)
    monkeypatch.setattr(
        provider,
        "_prepare_model_attempt",
        lambda _model, _agent, _agent_model, _owner_id, api_keys: (
            api_keys,
            SimpleNamespace(is_active=True),
            "system",
            0.3,
        ),
    )
    attempted_models = []

    async def invoke_model(model, *_args):
        attempted_models.append(model)
        if model is slow_model:
            raise TimeoutError("The first model timed out.")
        return "successful response", object()

    monkeypatch.setattr(provider, "_invoke_model", invoke_model)
    monkeypatch.setattr(provider, "_record_usage", lambda *_args: None)

    result = asyncio.run(provider.call_ai("prompt", agent_id))

    assert result == "successful response"
    assert attempted_models == [slow_model, fallback_model]


def test_ai_generation_returns_504_after_all_models_time_out(monkeypatch):
    from app.modules.ai_provider.services import ai_compatibility_layer

    user_id = uuid4()
    agent_id = uuid4()
    model = SimpleNamespace(
        id=uuid4(), display_name="Timed out model", id_ai_provider=uuid4()
    )
    context = (
        user_id,
        SimpleNamespace(id=agent_id),
        object(),
        [(model, 1.0, object())],
        None,
        {model.id: [object()]},
        {},
    )
    provider = ai_compatibility_layer.AiProvider(cast(Session, object()), "token")
    monkeypatch.setattr(provider, "_prepare_call_context", lambda *_args: context)
    monkeypatch.setattr(
        provider,
        "_prepare_model_attempt",
        lambda _model, _agent, _agent_model, _owner_id, api_keys: (
            api_keys,
            SimpleNamespace(is_active=True),
            "system",
            0.3,
        ),
    )

    async def invoke_model(*_args):
        raise TimeoutError("The model call timed out.")

    monkeypatch.setattr(provider, "_invoke_model", invoke_model)

    with pytest.raises(HTTPException) as error:
        asyncio.run(provider.call_ai("prompt", agent_id))

    assert error.value.status_code == 504
    assert "timed out" in error.value.detail.lower()


@pytest.mark.parametrize(
    (
        "model_slug",
        "provider_slug",
        "expected_provider",
        "expected_method",
        "expected_client_options",
    ),
    [
        ("test-model", "google", "google_genai", None, {}),
        (
            "openai/gpt-oss-120b",
            "groq",
            "groq",
            "json_mode",
            {"max_retries": 0, "timeout": 270},
        ),
    ],
)
def test_invalid_structured_response_is_retried_and_validated(
    monkeypatch,
    model_slug,
    provider_slug,
    expected_provider,
    expected_method,
    expected_client_options,
):
    from app.modules.ai_provider.models import CreateFlashcard
    from app.modules.ai_provider.services import ai_compatibility_layer

    prompts = []
    system_prompts = []
    structured_methods = []
    model_options = []

    class Prompt:
        def __or__(self, _structured_model):
            return self

        async def ainvoke(self, values):
            prompts.append(values["user_prompt"])
            if len(prompts) == 1:
                return {
                    "parsed": None,
                    "raw": SimpleNamespace(
                        content=[{"type": "text", "text": "not valid JSON"}]
                    ),
                    "parsing_error": ValueError("invalid structured output"),
                }
            return {
                "parsed": {
                    "title": "Title",
                    "statement": "Statement",
                    "target_skill": "Recall",
                },
                "raw": SimpleNamespace(content="{}"),
                "parsing_error": None,
            }

    class PromptTemplate:
        @staticmethod
        def from_messages(messages):
            system_prompts.append(messages[0][1])
            return Prompt()

    class ChatModel:
        def with_structured_output(
            self, _response_model, include_raw, **options
        ):
            assert include_raw is True
            structured_methods.append(options.get("method"))
            return object()

    model_providers = []

    def init_chat_model(*_args, **kwargs):
        model_providers.append(kwargs["model_provider"])
        model_options.append(
            {
                key: kwargs[key]
                for key in ("max_retries", "timeout")
                if key in kwargs
            }
        )
        return ChatModel()

    monkeypatch.setattr(
        ai_compatibility_layer,
        "_import_langchain",
        lambda: (init_chat_model, PromptTemplate),
    )
    monkeypatch.setattr(ai_compatibility_layer, "decrypt", lambda _key: "api-key")

    result, _raw = asyncio.run(
        ai_compatibility_layer.AiProvider(object(), "token")._invoke_model(
            model=SimpleNamespace(slug=model_slug, display_name="Test model"),
            api_keys=[SimpleNamespace(encrypted_key="encrypted")],
            provider=SimpleNamespace(protocol="native", slug=provider_slug),
            system_prompt="Return a flashcard.",
            temperature=0.3,
            user_prompt="Create one flashcard.",
            response_model=CreateFlashcard,
        )
    )

    assert isinstance(result, CreateFlashcard)
    assert result.title == "Title"
    assert model_providers == [expected_provider]
    assert structured_methods == [expected_method]
    assert model_options == [expected_client_options]
    if expected_method == "json_mode":
        assert "Return only JSON matching the following JSON Schema:" in system_prompts[0]
        assert '"target_skill"' in system_prompts[0]
        assert "{{" in system_prompts[0]
        assert "}}" in system_prompts[0]
    assert len(prompts) == 2
    assert "did not satisfy the required CreateFlashcard data model" in prompts[1]
    assert "not valid JSON" in prompts[1]


def test_key_failover_does_not_duplicate_gpt_oss_schema_in_system_prompt(
    monkeypatch,
):
    from app.modules.ai_provider.models import CreateFlashcard
    from app.modules.ai_provider.services import ai_compatibility_layer

    system_prompts = []

    class Chain:
        def __init__(self, api_key):
            self.api_key = api_key

        async def ainvoke(self, _values):
            if self.api_key == "first-key":
                raise RuntimeError("The first key is unavailable.")
            return {
                "parsed": {"title": "Title", "statement": "Statement"},
                "raw": object(),
            }

    class Prompt:
        def __or__(self, structured_model):
            return Chain(structured_model.api_key)

    class PromptTemplate:
        @staticmethod
        def from_messages(messages):
            system_prompts.append(messages[0][1])
            return Prompt()

    class ChatModel:
        def __init__(self, api_key):
            self.api_key = api_key

        def with_structured_output(self, *_args, **_kwargs):
            return SimpleNamespace(api_key=self.api_key)

    def init_chat_model(*_args, api_key, **_kwargs):
        return ChatModel(api_key)

    monkeypatch.setattr(
        ai_compatibility_layer,
        "_import_langchain",
        lambda: (init_chat_model, PromptTemplate),
    )
    monkeypatch.setattr(ai_compatibility_layer, "decrypt", lambda key: key)

    result, _raw = asyncio.run(
        ai_compatibility_layer.AiProvider(object(), "token")._invoke_model(
            model=SimpleNamespace(
                slug="openai/gpt-oss-120b",
                display_name="Test model",
            ),
            api_keys=[
                SimpleNamespace(encrypted_key="first-key"),
                SimpleNamespace(encrypted_key="second-key"),
            ],
            provider=SimpleNamespace(protocol="native", slug="openai"),
            system_prompt="Return a flashcard.",
            temperature=0.3,
            user_prompt="Create one flashcard.",
            response_model=CreateFlashcard,
        )
    )

    assert isinstance(result, CreateFlashcard)
    assert len(system_prompts) == 2
    assert system_prompts[0] == system_prompts[1]
    assert system_prompts[0].count(
        "Return only JSON matching the following JSON Schema:"
    ) == 1


def test_langchain_import_does_not_block_the_event_loop(monkeypatch):
    import time

    from app.core.db_models.ai_models import AiModel, UserApiKey
    from app.modules.ai_provider.models import CreateFlashcard
    from app.modules.ai_provider.services import ai_compatibility_layer

    class Chain:
        async def ainvoke(self, _values):
            return {
                "parsed": {"title": "Title", "statement": "Statement"},
                "raw": object(),
            }

    class Prompt:
        def __or__(self, _structured_model):
            return Chain()

    class PromptTemplate:
        @staticmethod
        def from_messages(_messages):
            return Prompt()

    class ChatModel:
        def with_structured_output(self, *_args, **_kwargs):
            return object()

    def init_chat_model(*_args, **_kwargs):
        return ChatModel()

    def slow_import():
        time.sleep(0.1)
        return init_chat_model, PromptTemplate

    monkeypatch.setattr(ai_compatibility_layer, "_import_langchain", slow_import)
    monkeypatch.setattr(ai_compatibility_layer, "decrypt", lambda _key: "api-key")
    provider = ai_compatibility_layer.AiProvider(cast(Session, object()), "token")

    async def verify_responsiveness():
        generation = asyncio.create_task(
            provider._invoke_model(
                model=cast(
                    AiModel,
                    SimpleNamespace(slug="test-model", display_name="Test model"),
                ),
                api_keys=[
                    cast(UserApiKey, SimpleNamespace(encrypted_key="encrypted"))
                ],
                provider=SimpleNamespace(protocol="native", slug="openai"),
                system_prompt="Return a flashcard.",
                temperature=0.3,
                user_prompt="Create one flashcard.",
                response_model=CreateFlashcard,
            )
        )
        await asyncio.sleep(0.01)
        assert not generation.done()
        parsed, _raw = await generation
        assert parsed == CreateFlashcard(title="Title", statement="Statement")

    asyncio.run(verify_responsiveness())


def test_model_timeout_still_allows_the_next_api_key_to_succeed(monkeypatch):
    from app.core.db_models.ai_models import AiModel, UserApiKey
    from app.modules.ai_provider.models import CreateFlashcard
    from app.modules.ai_provider.services import ai_compatibility_layer

    attempted_keys = []

    class Chain:
        def __init__(self, api_key):
            self.api_key = api_key

        async def ainvoke(self, _values):
            if self.api_key == "slow-key":
                await asyncio.sleep(0.075)
            return {
                "parsed": {"title": "Title", "statement": "Statement"},
                "raw": object(),
            }

    class Prompt:
        def __or__(self, structured_model):
            return Chain(structured_model.api_key)

    class PromptTemplate:
        @staticmethod
        def from_messages(_messages):
            return Prompt()

    class ChatModel:
        def __init__(self, api_key):
            self.api_key = api_key

        def with_structured_output(self, *_args, **_kwargs):
            return SimpleNamespace(api_key=self.api_key)

    def init_chat_model(*_args, api_key, **_kwargs):
        attempted_keys.append(api_key)
        return ChatModel(api_key)

    monkeypatch.setattr(
        ai_compatibility_layer,
        "_import_langchain",
        lambda: (init_chat_model, PromptTemplate),
    )
    monkeypatch.setattr(
        ai_compatibility_layer,
        "AI_MODEL_REQUEST_TIMEOUT_SECONDS",
        0.1,
    )
    monkeypatch.setattr(ai_compatibility_layer, "decrypt", lambda key: key)
    provider = ai_compatibility_layer.AiProvider(cast(Session, object()), "token")

    result, _raw = asyncio.run(
        provider._invoke_model(
            model=cast(
                AiModel,
                SimpleNamespace(slug="test-model", display_name="Test model"),
            ),
            api_keys=[
                cast(UserApiKey, SimpleNamespace(encrypted_key="slow-key")),
                cast(UserApiKey, SimpleNamespace(encrypted_key="fast-key")),
            ],
            provider=SimpleNamespace(protocol="native", slug="openai"),
            system_prompt="Return a flashcard.",
            temperature=0.3,
            user_prompt="Create one flashcard.",
            response_model=CreateFlashcard,
        )
    )

    assert result == CreateFlashcard(title="Title", statement="Statement")
    assert attempted_keys == ["slow-key", "fast-key"]


def test_malformed_tool_error_does_not_expose_generated_arguments():
    from app.modules.ai_provider.services.ai_compatibility_layer import (
        _format_provider_error,
    )

    message = _format_provider_error(
        RuntimeError(
            "tool_use_failed: failed_generation={'private_argument': 'model output'}"
        )
    )

    assert "private_argument" not in message
    assert "model output" not in message


def test_ai_generation_timeout_returns_gateway_timeout(monkeypatch):
    from app.modules.ai_provider import router

    class TimedOutProvider:
        async def call_ai(self, **_kwargs):
            raise TimeoutError("The model call timed out.")

    monkeypatch.setattr(router, "AiProvider", lambda **_kwargs: TimedOutProvider())

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            router.use_ai(
                user_prompt="prompt",
                agent_id=uuid4(),
                response_language=None,
                token="token",
                db=object(),
            )
        )

    assert error.value.status_code == 504
    assert "timed out" in error.value.detail.lower()


def test_ai_generation_timeout_layers_allow_the_model_deadline_to_unwind():
    from app.modules.ai_provider.services import ai_compatibility_layer

    assert ai_compatibility_layer.AI_MODEL_REQUEST_TIMEOUT_SECONDS == 240
    assert (
        ai_compatibility_layer.AI_MODEL_HTTP_TIMEOUT_SECONDS
        > ai_compatibility_layer.AI_MODEL_REQUEST_TIMEOUT_SECONDS
    )


def test_ai_generation_database_work_does_not_block_event_loop(monkeypatch):
    from app.modules.ai_provider.models import CreateFlashcard
    from app.modules.ai_provider.services.ai_compatibility_layer import AiProvider

    provider = AiProvider(object(), "token")

    def slow_prepare(_agent_id, _response_language):
        import time

        time.sleep(0.1)
        return uuid4(), object(), CreateFlashcard, [], None, {}, {}

    monkeypatch.setattr(provider, "_prepare_call_context", slow_prepare)

    async def verify_responsiveness():
        generation = asyncio.create_task(
            provider.call_ai("prompt", uuid4())
        )
        await asyncio.sleep(0.01)
        assert not generation.done()
        with pytest.raises(RuntimeError, match="No models are configured"):
            await generation

    asyncio.run(verify_responsiveness())


def test_structured_response_still_rejects_missing_required_fields():
    from app.modules.ai_provider.models import CreateFlashcard
    from app.modules.ai_provider.services.ai_compatibility_layer import AiProvider

    with pytest.raises(ValueError, match="does not match CreateFlashcard"):
        AiProvider(object(), "token")._parse_model_result(
            {
                "parsed": {"title": "Title"},
                "raw": None,
            },
            CreateFlashcard,
        )


def test_invalid_json_diagnostic_does_not_include_model_output(monkeypatch):
    from app.modules.ai_provider.services import jsonServices

    def fail_repair(_text):
        raise ValueError("could not repair")

    monkeypatch.setattr(jsonServices, "repair_json_loads", fail_repair)
    raw_output = "private-response-fragment"

    with pytest.raises(ValueError) as error:
        jsonServices.JsonHelper._decode_json(raw_output)

    assert raw_output not in str(error.value)


def test_shared_api_key_is_encrypted_and_never_returned(monkeypatch):
    from app.modules.ai import services
    from app.modules.ai.models import SharedApiKeyCreate, SharedApiKeyOut

    provider_id = uuid4()
    monkeypatch.setattr(
        services, "get_provider", lambda _provider_id, _db: SimpleNamespace()
    )
    encrypted_values = []

    def encrypt(api_key):
        encrypted_values.append(api_key)
        return "encrypted-replacement"

    monkeypatch.setattr(services, "encrypt", encrypt)

    class Db:
        added = None

        def add(self, value):
            self.added = value

        def commit(self):
            pass

        def refresh(self, _value):
            pass

    db = Db()
    created = services.create_shared_api_key(
        SharedApiKeyCreate(
            id_ai_provider=provider_id,
            name="Primary shared key",
            api_key="provider-secret",
        ),
        db,
    )
    response = SharedApiKeyOut.model_validate(created)

    assert db.added is created
    assert created.encrypted_key == "encrypted-replacement"
    assert encrypted_values == ["provider-secret"]
    assert "provider-secret" not in response.model_dump_json()


def test_shared_api_key_update_encrypts_replacement(monkeypatch):
    from app.modules.ai import services
    from app.modules.ai.models import SharedApiKeyUpdate

    shared_key = SimpleNamespace(
        id=uuid4(),
        id_ai_provider=uuid4(),
        name="Shared key",
        encrypted_key="old-encrypted-key",
        is_active=True,
        updated_at=None,
    )
    monkeypatch.setattr(
        services, "get_shared_api_key", lambda _id, _db: shared_key
    )
    encrypted_values = []

    def encrypt(api_key):
        encrypted_values.append(api_key)
        return "encrypted-replacement"

    monkeypatch.setattr(services, "encrypt", encrypt)

    class Db:
        def commit(self):
            pass

        def refresh(self, _value):
            pass

    updated = services.update_shared_api_key(
        str(shared_key.id),
        SharedApiKeyUpdate(api_key="replacement-secret", is_active=False),
        Db(),
    )

    assert updated.encrypted_key == "encrypted-replacement"
    assert updated.is_active is False
    assert encrypted_values == ["replacement-secret"]
    assert "replacement-secret" not in repr(updated)


def test_response_language_uses_preference_then_global_setting():
    from app.modules.ai_provider.services.ai_compatibility_layer import AiProvider

    class Db:
        def __init__(self):
            self.results = iter((None, "Português"))
            self.statements = []

        def scalar(self, statement):
            self.statements.append(str(statement))
            return next(self.results)

    db = Db()
    language = AiProvider(db, "token")._get_response_language(uuid4())

    assert language == "Português"
    assert len(db.statements) == 2
    assert "response_language_preference_order" in db.statements[0]
    assert "preference_order IS NOT NULL" in db.statements[0]
    assert "user_global_config" in db.statements[1]


@pytest.mark.asyncio
async def test_ai_route_forwards_a_validated_response_language(monkeypatch):
    from app.modules.ai_provider import router

    class Db:
        def scalar(self, _statement):
            return "English"

    class Provider:
        def __init__(self, *, db, user_token):
            assert db is not None
            assert user_token == "token"

        async def call_ai(self, *, agent_id, user_prompt, response_language):
            assert agent_id == uuid4_value
            assert user_prompt == "prompt"
            assert response_language == "English"
            return {"response": "ok"}

    uuid4_value = uuid4()
    monkeypatch.setattr(router, "AiProvider", Provider)

    result = await router.use_ai(
        user_prompt="prompt",
        agent_id=uuid4_value,
        response_language="english",
        token="token",
        db=Db(),
    )

    assert result == {"response": "ok"}


def test_study_assistant_response_schema_includes_frontend_actions():
    from app.modules.ai_provider.models import StudyAssistentResponse

    response = StudyAssistentResponse.model_validate(
        {
            "feedback": "Vamos criar um mapa.",
            "actions": [
                {
                    "type": "create_graph",
                    "title": "Mapa sobre biologia",
                    "prompt": "Biologia celular",
                }
            ],
        }
    )

    assert response.actions[0].type == "create_graph"
    assert response.actions[0].prompt == "Biologia celular"
