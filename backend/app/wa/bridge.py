"""Starts/stops the Node WhatsApp bridge and talks to it over localhost with a shared secret."""
import logging
import os
import subprocess
import threading

import httpx

from ..core.config import get_settings

log = logging.getLogger(__name__)
_proc: subprocess.Popen | None = None
_lock = threading.Lock()


class BridgeError(RuntimeError):
    pass


def _headers() -> dict:
    return {"x-bridge-secret": get_settings().bridge_secret}


def running() -> bool:
    try:
        return httpx.get(f"{get_settings().bridge_url}/status", headers=_headers(), timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def start() -> None:
    global _proc
    st = get_settings()
    if not st.bridge_secret or not st.wa_session_key:
        raise BridgeError("BRIDGE_SECRET / WA_SESSION_KEY missing in backend/.env")
    with _lock:
        if running():
            return
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "APPDATA")}
        env.update(BRIDGE_SECRET=st.bridge_secret, WA_SESSION_KEY=st.wa_session_key,
                   BACKEND_URL="http://127.0.0.1:8100", BRIDGE_PORT=st.bridge_url.rsplit(":", 1)[-1],
                   WA_SESSION_DIR=str(st.storage_dir / "whatsapp_sessions" / "default"), MEDIA_ENABLED="0")
        logf = open(st.storage_dir / "wa-bridge.log", "ab")
        _proc = subprocess.Popen([st.node_exe, "src/bridge.js"], cwd=st.bridge_dir, env=env, stdout=logf,
                                 stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(40):
        if running():
            return
        threading.Event().wait(0.25)
    raise BridgeError("bridge did not start; see storage/wa-bridge.log")


def stop() -> None:
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
    _proc = None


def call(method: str, path: str, body: dict | None = None) -> dict:
    try:
        r = httpx.request(method, f"{get_settings().bridge_url}{path}", json=body, headers=_headers(), timeout=30)
    except httpx.HTTPError as exc:
        raise BridgeError(f"bridge not reachable ({type(exc).__name__})") from exc
    if r.status_code >= 300:
        raise BridgeError(r.json().get("error", r.text[:200]))
    return r.json()
