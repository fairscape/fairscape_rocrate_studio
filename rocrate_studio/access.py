"""Who is using the studio, for a shared (deployed) studio. All of it is off by default.

The studio is a local tool: one person, one output folder, no sign-in. A
deployed copy can turn on either of two things, separately:

* ``ROCRATE_STUDIO_MULTI_USER=1`` (``--multi-user``) asks each visitor for a
  name or email and gives them their own output folder,
  ``<out>/users/<name>/``, so one visitor opening an example does not delete
  the copy another is working in. It is a convenience, not isolation: the file
  browser and Save still reach the whole machine, and a banner says so.
* ``ROCRATE_STUDIO_PASSWORD`` (``--password``) is one shared password every
  visitor has to give before any ``/api`` call works.

Either one signs the visitor in with a cookie, signed with a key made at
startup, so a restart signs everyone out (a deployed studio is wiped then too).
"""
from __future__ import annotations

import contextvars
import hashlib
import hmac
import os
import re
import secrets
from http.cookies import SimpleCookie
from pathlib import Path

COOKIE = "studio_session"
_KEY = secrets.token_bytes(32)
_user: contextvars.ContextVar[str | None] = contextvars.ContextVar("studio_user", default=None)

#: paths that work before signing in: the page itself and the sign-in calls
OPEN_PATHS = ("/api/session", "/api/login", "/api/logout")


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def multi_user() -> bool:
    return _flag("ROCRATE_STUDIO_MULTI_USER")


def password() -> str:
    return os.environ.get("ROCRATE_STUDIO_PASSWORD", "")


def enabled() -> bool:
    return multi_user() or bool(password())


def slug(name: str) -> str:
    """A visitor's name or email as a folder name: ``Jo.Smith@uva.edu`` -> ``jo.smith-uva.edu``."""
    s = re.sub(r"[^a-z0-9._-]+", "-", name.strip().lower()).strip("-.")
    return s[:64] or "guest"


def _sign(user: str) -> str:
    return hmac.new(_KEY, user.encode(), hashlib.sha256).hexdigest()[:32]


def cookie_value(user: str) -> str:
    return f"{user}|{_sign(user)}"


def user_from_cookie(header: str | None) -> str | None:
    if not header:
        return None
    jar = SimpleCookie()
    try:
        jar.load(header)
    except Exception:  # noqa: BLE001
        return None
    morsel = jar.get(COOKIE)
    if not morsel or "|" not in morsel.value:
        return None
    user, sig = morsel.value.rsplit("|", 1)
    return user if hmac.compare_digest(sig, _sign(user)) else None


def check_password(given: str) -> bool:
    want = password()
    return not want or hmac.compare_digest(given.encode(), want.encode())


def current_user() -> str | None:
    return _user.get()


def user_dir(base: Path) -> Path:
    """The output folder for whoever is making this request."""
    user = _user.get()
    if multi_user() and user:
        return base / "users" / user
    return base


class Gate:
    """ASGI middleware: refuse ``/api`` calls without a valid sign-in cookie
    (when sign-in is on) and remember who is asking for :func:`user_dir`."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not enabled():
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        user = user_from_cookie(headers.get(b"cookie", b"").decode("latin-1"))
        path = scope.get("path", "")
        if user is None and path.startswith("/api/") and path not in OPEN_PATHS:
            body = b'{"detail":"sign in first","signin":true}'
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        token = _user.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            _user.reset(token)
