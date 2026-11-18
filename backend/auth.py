"""
Lecturer access control: one shared lecturer password (LECTURER_PASSWORD env
var) guarding every /api/lecturer/* route -- see main.py's lecturer_auth
middleware.

Two ways to prove you're the lecturer:
  - the lecturer pages log in once (POST /api/lecturer/login) and get a session
    cookie: "<issued unix time>.<HMAC of it>", keyed on the password, valid for
    SESSION_SECONDS. Nothing is stored server-side, so sessions survive a
    restart, and changing the password logs everyone out.
  - scripts send the password itself in an X-Lecturer-Token header.

LECTURER_PASSWORD unset means no lecturer auth at all (local development, the
smoke test, the seed scripts) -- main.py logs a warning at startup, since a
server students can reach must never run that way.

Students never log in: they get a per-lecture token when they join (see
store.join_student()).
"""

import hashlib
import hmac
import os
import secrets
import time

COOKIE_NAME = "lecturer_session"
HEADER_NAME = "X-Lecturer-Token"
SESSION_SECONDS = 12 * 60 * 60  # a teaching day


def password() -> str | None:
    """Read on every request (not cached at import), so tests can set it."""
    return os.environ.get("LECTURER_PASSWORD") or None


def auth_required() -> bool:
    return password() is not None


def password_matches(candidate: str) -> bool:
    expected = password()
    return expected is not None and secrets.compare_digest(candidate.encode(), expected.encode())


def _sign(issued: str, key: str) -> str:
    return hmac.new(key.encode(), f"lecturer-session:{issued}".encode(), hashlib.sha256).hexdigest()


def new_session_cookie() -> str:
    issued = str(int(time.time()))
    return f"{issued}.{_sign(issued, password())}"


def session_valid(cookie: str | None) -> bool:
    key = password()
    if not key or not cookie or "." not in cookie:
        return False
    issued, signature = cookie.split(".", 1)
    if not issued.isdigit() or not secrets.compare_digest(signature, _sign(issued, key)):
        return False
    return 0 <= time.time() - int(issued) < SESSION_SECONDS


def is_lecturer(cookie: str | None, header: str | None) -> bool:
    """Whether a request comes from the lecturer. Always True with auth off."""
    if not auth_required():
        return True
    return session_valid(cookie) or (header is not None and password_matches(header))
