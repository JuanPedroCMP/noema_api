import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
import socket

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
    ):
        for operation in paths[path].values():
            assert "security" in operation


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
        "_get_api_keys",
        lambda _self, model: [personal_key] if model is model_with_key else [],
    )
    monkeypatch.setattr(
        ai_compatibility_layer.AiProvider,
        "_get_shared_api_keys",
        lambda _self, model: (
            [shared_key] if model is model_with_shared_key else []
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
        assert db.commits >= 4
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
    assert provider_lookups == [
        str(model_with_key.id_ai_provider),
        str(model_with_shared_key.id_ai_provider),
    ]
    assert invoked_models == [model_with_key, model_with_shared_key]
    assert invoked_keys == [[personal_key], [shared_key]]
    assert all("Respond in Portuguese." in prompt for prompt in invoked_prompts)


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
            {"max_retries": 0, "timeout": 240},
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
    from app.modules.ai_provider.services import ai_compatibility_layer
    from app.modules.ai_provider.models import CreateFlashcard

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

    class HungProvider:
        async def call_ai(self, **_kwargs):
            await asyncio.sleep(1)

    monkeypatch.setattr(
        router, "AiProvider", lambda **_kwargs: HungProvider()
    )
    monkeypatch.setattr(router, "AI_GENERATION_TIMEOUT_SECONDS", 0.001)

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


def test_ai_generation_timeout_is_four_minutes():
    from app.modules.ai_provider import router
    from app.modules.ai_provider.services import ai_compatibility_layer

    assert router.AI_GENERATION_TIMEOUT_SECONDS == 240
    assert ai_compatibility_layer.AI_MODEL_REQUEST_TIMEOUT_SECONDS == 240
    assert ai_compatibility_layer.AI_MODEL_HTTP_TIMEOUT_SECONDS == 240


def test_ai_generation_database_work_does_not_block_event_loop(monkeypatch):
    from app.modules.ai_provider.models import CreateFlashcard
    from app.modules.ai_provider.services.ai_compatibility_layer import AiProvider

    provider = AiProvider(object(), "token")

    def slow_prepare(_agent_id, _response_language):
        import time

        time.sleep(0.1)
        return uuid4(), object(), CreateFlashcard, [], None

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
    from app.modules.ai_provider.services.ai_compatibility_layer import AiProvider
    from app.modules.ai_provider.models import CreateFlashcard

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
