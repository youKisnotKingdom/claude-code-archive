from fastapi.testclient import TestClient

from cc_history.config import settings
from cc_history.main import app


def test_auth_is_disabled_without_password(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_password", None)

    response = TestClient(app).get("/")

    assert response.status_code == 200


def test_auth_redirects_html_requests_when_password_is_set(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_password", "secret")

    response = TestClient(app).get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_auth_rejects_api_requests_when_password_is_set(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_password", "secret")

    response = TestClient(app).get("/api/users")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_login_sets_cookie_and_allows_access(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_password", "secret")

    client = TestClient(app)
    login_response = client.post("/login", data={"password": "secret"}, follow_redirects=False)
    home_response = client.get("/")

    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/"
    assert home_response.status_code == 200


def test_login_rejects_wrong_password(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_password", "secret")

    response = TestClient(app).post("/login", data={"password": "wrong"})

    assert response.status_code == 401
    assert "Invalid password" in response.text
