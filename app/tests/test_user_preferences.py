from email import message_from_string
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import oauth2_scheme
from app.modules.auth import service as auth_service
from app.modules.user_config import preferences as preferences_service

USER_ID = UUID("b08c5a73-2437-4e15-8a3c-d46e010f2367")


def test_preferences_endpoint_requires_bearer_authentication():
    from app.main import app

    app.dependency_overrides[get_db] = lambda: FakeDB()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/user_config/preferences")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


class FakeDB:
    def __init__(self, record=None):
        self.record = record
        self.added = []
        self.commits = 0

    def scalar(self, _statement):
        return self.record

    def add(self, value):
        self.added.append(value)
        self.record = value

    def commit(self):
        self.commits += 1

    def refresh(self, instance=None, **_kwargs):
        return None

    def rollback(self):
        return None


def test_preferences_endpoints_are_authenticated_and_replace_user_preferences(
    monkeypatch,
):
    from app.main import app

    db = FakeDB()
    user = SimpleNamespace(id=USER_ID)
    monkeypatch.setattr(
        preferences_service, "get_current_user", lambda token, _db: user
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[oauth2_scheme] = lambda: "valid-token"
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/user_config/preferences")
            assert response.status_code == 200
            assert response.json() == {
                "id_user": str(USER_ID),
                "preferences": {},
                "updated_at": None,
            }

            response = client.put(
                "/api/v1/user_config/preferences",
                json={
                    "preferences": {
                        "backupFrequency": "weekly",
                        "timezone": "America/Sao_Paulo",
                    }
                },
            )
            assert response.status_code == 200
            assert response.json()["id_user"] == str(USER_ID)
            assert response.json()["preferences"] == {
                "backupFrequency": "weekly",
                "timezone": "America/Sao_Paulo",
            }
            assert db.commits == 1

            persisted = client.get("/api/v1/user_config/preferences")
            assert persisted.status_code == 200
            assert persisted.json()["preferences"] == {
                "backupFrequency": "weekly",
                "timezone": "America/Sao_Paulo",
            }

            patched = client.patch(
                "/api/v1/user_config/preferences",
                json={"preferences": {"timezone": "Europe/Paris"}},
            )
            assert patched.status_code == 200
            assert patched.json()["preferences"] == {
                "backupFrequency": "weekly",
                "timezone": "Europe/Paris",
            }

            scheduled = client.put(
                "/api/v1/user_config/preferences",
                json={
                    "preferences": {
                        "backupFrequency": "manual",
                        "backupSchedule": {"unit": "hours", "interval": 4},
                        "backupOnExit": True,
                    }
                },
            )
            assert scheduled.status_code == 200
            assert scheduled.json()["preferences"]["backupFrequency"] == "manual"
            assert scheduled.json()["preferences"]["backupSchedule"] == {
                "unit": "hours",
                "interval": 4,
            }
            assert scheduled.json()["preferences"]["backupOnExit"] is True

            invalid_timezone = client.put(
                "/api/v1/user_config/preferences",
                json={"preferences": {"timezone": "Mars/Olympus_Mons"}},
            )
            assert invalid_timezone.status_code == 422
            invalid_frequency = client.put(
                "/api/v1/user_config/preferences",
                json={"preferences": {"backupFrequency": "hourly"}},
            )
            assert invalid_frequency.status_code == 422
            invalid_frequency_type = client.put(
                "/api/v1/user_config/preferences",
                json={"preferences": {"backupFrequency": []}},
            )
            assert invalid_frequency_type.status_code == 422
            invalid_backup_schedule = client.put(
                "/api/v1/user_config/preferences",
                json={
                    "preferences": {
                        "backupSchedule": {"unit": "hours", "interval": 25}
                    }
                },
            )
            assert invalid_backup_schedule.status_code == 422
            invalid_backup_schedule_unit = client.put(
                "/api/v1/user_config/preferences",
                json={"preferences": {"backupSchedule": {"unit": [], "interval": 1}}},
            )
            assert invalid_backup_schedule_unit.status_code == 422
            invalid_backup_on_exit = client.put(
                "/api/v1/user_config/preferences",
                json={"preferences": {"backupOnExit": "yes"}},
            )
            assert invalid_backup_on_exit.status_code == 422

        schema = app.openapi()
        route = schema["paths"]["/api/v1/user_config/preferences"]
        assert "security" in route["get"]
        assert "security" in route["put"]
        assert "security" in route["patch"]
        assert (
            route["put"]["requestBody"]["content"]["application/json"]["schema"][
                "$ref"
            ]
            == "#/components/schemas/UserPreferencesUpdate"
        )
    finally:
        app.dependency_overrides.clear()


def test_password_reset_email_includes_local_and_utc_times(monkeypatch):
    preferences = SimpleNamespace(preferences={"timezone": "America/Sao_Paulo"})
    db = FakeDB(record=preferences)
    user = SimpleNamespace(id=USER_ID, primary_email="student@example.com")
    sent = {}

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def starttls(self):
            return None

        def login(self, *_args):
            return None

        def sendmail(self, _sender, _recipient, content):
            sent["message"] = content

    monkeypatch.setattr(
        auth_service, "get_user_by_identificator", lambda **_kwargs: user
    )
    monkeypatch.setattr(auth_service, "load_dotenv", lambda **_kwargs: None)
    monkeypatch.setattr(auth_service.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_USERNAME", "no-reply@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "test-password")

    auth_service.start_reset_password("student", db)

    message = message_from_string(sent["message"])
    plain_text = next(
        part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
        for part in message.walk()
        if part.get_content_type() == "text/plain"
    )
    assert "hora local — America/Sao_Paulo" in plain_text
    assert "Solicitado em (UTC):" in plain_text
    assert "Expira em (UTC):" in plain_text


def test_language_list_exposes_explicit_native_translation_flag():
    from app.main import app

    language_id = UUID("a275d698-0624-4917-941d-b9909f31d7b6")
    language = SimpleNamespace(
        id=language_id,
        name="English",
        percentage_translated=100,
        verified_translation=True,
        automatic_translation=False,
        is_native=True,
        created_at=None,
        updated_at=None,
    )

    class LanguageDB(FakeDB):
        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [language])

    app.dependency_overrides[get_db] = lambda: LanguageDB()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/user_config/language/list")

        assert response.status_code == 200
        assert response.json()[0]["is_native"] is True
    finally:
        app.dependency_overrides.clear()
