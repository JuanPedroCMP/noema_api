from types import SimpleNamespace

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
