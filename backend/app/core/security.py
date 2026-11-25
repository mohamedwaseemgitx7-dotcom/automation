"""Owner auth: PBKDF2 password hash, HMAC-signed session cookie, double-submit CSRF token."""
import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException, Request

from .config import get_settings

COOKIE = "agent_session"
CSRF_COOKIE = "agent_csrf"
SESSION_TTL = 12 * 3600
ITERATIONS = 600_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def _sign(data: bytes) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def make_session(username: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"u": username, "exp": int(time.time()) + SESSION_TTL}).encode())
    return f"{body.decode()}.{_sign(body)}"


def read_session(token: str | None) -> str | None:
    if not token or "." not in token or not get_settings().secret_key:
        return None
    body, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(body.encode())):
        return None
    data = json.loads(base64.urlsafe_b64decode(body))
    return data["u"] if data.get("exp", 0) > time.time() else None


def require_owner(request: Request) -> str:
    user = read_session(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "login required")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        sent, cookie = request.headers.get("x-csrf-token", ""), request.cookies.get(CSRF_COOKIE, "")
        if not cookie or not hmac.compare_digest(sent, cookie):
            raise HTTPException(403, "csrf check failed")
    return user
