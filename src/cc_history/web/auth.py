import hashlib
import hmac
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from cc_history.config import settings

AUTH_EXEMPT_PATHS = {"/login", "/logout"}
AUTH_TOKEN_MESSAGE = b"cc-history-viewer-auth-token"


def auth_enabled() -> bool:
    return settings.auth_password is not None and settings.auth_password != ""


def make_auth_token() -> str:
    password = settings.auth_password or ""
    return hmac.new(password.encode("utf-8"), AUTH_TOKEN_MESSAGE, hashlib.sha256).hexdigest()


def request_is_authenticated(request: Request) -> bool:
    if not auth_enabled():
        return True
    cookie_value = request.cookies.get(settings.auth_cookie_name)
    if cookie_value is None:
        return False
    return secrets.compare_digest(cookie_value, make_auth_token())


def authenticate_password(password: str) -> bool:
    expected = settings.auth_password or ""
    return secrets.compare_digest(password, expected)


def set_auth_cookie(response: Response) -> None:
    response.set_cookie(
        settings.auth_cookie_name,
        make_auth_token(),
        httponly=True,
        samesite="lax",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(settings.auth_cookie_name)


def path_is_exempt(path: str) -> bool:
    return path in AUTH_EXEMPT_PATHS or path.startswith("/static/")


def unauthenticated_response(path: str) -> Response:
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return RedirectResponse("/login", status_code=303)
