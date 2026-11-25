"""FastAPI app: owner API + built dashboard. Binds to 127.0.0.1 by default (see run script)."""
import json
import logging
import secrets
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from .core import db
from .core.config import ROOT, get_settings
from .core.security import (COOKIE, CSRF_COOKIE, SESSION_TTL, make_session, require_owner, verify_password)
from .llm import readiness
from .llm.agent import Agent
from .llm.ollama_client import Ollama
from .rag import ingestion

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
st = get_settings()
db.init()
app = FastAPI(title="Local AI WhatsApp Agent", docs_url=None, redoc_url=None, openapi_url=None)
TESTS_FILE = st.storage_dir / "test_questions.json"
_login_failures: dict[str, int] = {}


@app.middleware("http")
async def headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                               "connect-src 'self'; frame-ancestors 'none'")
    return resp


# ---------------- auth ----------------
class Login(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=200)


@app.post("/api/auth/login")
def login(body: Login, request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    if _login_failures.get(ip, 0) >= 10:
        raise HTTPException(429, "too many attempts; restart the server or wait")
    if not st.owner_password_hash or not st.secret_key:
        raise HTTPException(503, "owner password not set: run scripts/set_password.py")
    if body.username != st.owner_username or not verify_password(body.password, st.owner_password_hash):
        _login_failures[ip] = _login_failures.get(ip, 0) + 1
        raise HTTPException(401, "wrong username or password")
    _login_failures.pop(ip, None)
    kw = dict(httponly=True, samesite="strict", secure=st.cookie_secure, max_age=SESSION_TTL)
    response.set_cookie(COOKIE, make_session(body.username), **kw)
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(24), samesite="strict", secure=st.cookie_secure,
                        max_age=SESSION_TTL)
    with db.session() as s:
        db.audit(s, "owner", "login")
        s.commit()
    return {"ok": True}


@app.post("/api/auth/logout")
def logout(response: Response, user: str = Depends(require_owner)):
    response.delete_cookie(COOKIE)
    response.delete_cookie(CSRF_COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: str = Depends(require_owner)):
    return {"user": user}


# ---------------- status ----------------
@app.get("/api/status")
def status(user: str = Depends(require_owner)):
    o = Ollama()
    with db.session() as s:
        cfg = db.get_config(s)
        kb = s.scalar(select(db.KnowledgeBase).where(db.KnowledgeBase.active.is_(True)))
        chunks = s.scalar(select(func.count(db.KnowledgeChunk.id)).where(db.KnowledgeChunk.kb_id == kb.id)) if kb else 0
        files = s.scalar(select(func.count(db.KnowledgeFile.id)).where(db.KnowledgeFile.kb_id == kb.id,
                                                                       db.KnowledgeFile.status == "ok")) if kb else 0
        last = s.scalar(select(db.ReadinessRun).order_by(desc(db.ReadinessRun.id)).limit(1))
        wa = s.scalar(select(db.WaSession).limit(1))
        contacts = s.scalar(select(func.count(db.Contact.id))) or 0
        s.commit()
    names = {m["name"] for m in o.models()}
    return {
        "whatsapp": {"status": wa.status if wa else "disconnected", "account": wa.account if wa else ""},
        "knowledge": {"active": bool(kb), "name": kb.zip_name if kb else None, "files": files, "chunks": chunks},
        "llm": {"runtime": o.version(), "chat_model": st.chat_model, "chat_ready": st.chat_model in names,
                "embed_model": st.embed_model, "embed_ready": st.embed_model in names or f"{st.embed_model}:latest" in names,
                "loaded": [m["name"] for m in o.loaded()]},
        "role_configured": bool(cfg.role and cfg.business_name),
        "automation": cfg.auto_reply,
        "ready": bool(last and last.ready),
        "ready_at": last.at.isoformat() if last else None,
        "contacts": contacts,
    }


# ---------------- role / config ----------------
class ConfigIn(BaseModel):
    bot_name: str = Field("", max_length=80)
    role: str = Field("", max_length=200)
    business_name: str = Field("", max_length=160)
    business_description: str = Field("", max_length=4000)
    website: str = Field("", max_length=300)
    objective: str = Field("", max_length=2000)
    allowed_topics: list[str] = Field(default_factory=list, max_length=40)
    blocked_topics: list[str] = Field(default_factory=list, max_length=40)
    languages: list[str] = Field(default_factory=list, max_length=6)
    tone: str = Field("friendly and professional", max_length=60)
    max_words: int = Field(90, ge=20, le=300)
    handoff_message: str = Field(..., min_length=5, max_length=500)
    instructions: str = Field("", max_length=4000)
    image_understanding: bool = False
    voice_understanding: bool = False


FIELDS = list(ConfigIn.model_fields)


@app.get("/api/config")
def get_config(user: str = Depends(require_owner)):
    with db.session() as s:
        cfg = db.get_config(s)
        s.commit()
        return {f: getattr(cfg, f) for f in FIELDS} | {"auto_reply": cfg.auto_reply}


@app.put("/api/config")
def put_config(body: ConfigIn, user: str = Depends(require_owner)):
    with db.session() as s:
        cfg = db.get_config(s)
        for f, v in body.model_dump().items():
            setattr(cfg, f, v)
        db.audit(s, "owner", "config_saved")
        s.commit()
    return {"ok": True}


# ---------------- knowledge base ----------------
@app.post("/api/kb/upload")
async def upload(background: BackgroundTasks, file: UploadFile = File(...), user: str = Depends(require_owner)):
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(400, "upload one .zip file")
    limit = st.max_zip_mb << 20
    with db.session() as s:
        kb = db.KnowledgeBase(zip_name=Path(file.filename).name[:200], zip_sha256="", status="processing")
        s.add(kb)
        s.flush()
        kb_id = kb.id
        s.commit()
    dest = st.storage_dir / "uploads" / f"kb_{kb_id}_upload.zip"
    size = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > limit:
                f.close()
                dest.unlink(missing_ok=True)
                ingestion.delete_kb(kb_id)
                raise HTTPException(413, f"ZIP larger than {st.max_zip_mb} MB")
            f.write(chunk)
    with db.session() as s:
        kb = s.get(db.KnowledgeBase, kb_id)
        kb.zip_sha256 = ingestion.sha256(dest)
        db.audit(s, "owner", "kb_uploaded", kb_id=kb_id, size=size)
        s.commit()
    background.add_task(ingestion.process, kb_id, dest)
    return {"kb_id": kb_id}


@app.get("/api/kb")
def list_kb(user: str = Depends(require_owner)):
    with db.session() as s:
        kbs = s.scalars(select(db.KnowledgeBase).order_by(desc(db.KnowledgeBase.id)).limit(10)).all()
        out = []
        for kb in kbs:
            files = s.scalars(select(db.KnowledgeFile).where(db.KnowledgeFile.kb_id == kb.id)).all()
            out.append({"id": kb.id, "name": kb.zip_name, "status": kb.status, "active": kb.active,
                        "progress": kb.progress, "message": kb.message, "created_at": kb.created_at.isoformat(),
                        "files": [{"path": f.path, "kind": f.kind, "status": f.status, "chunks": f.chunks,
                                   "error": f.error} for f in files]})
        return out


@app.post("/api/kb/{kb_id}/reindex")
def reindex(kb_id: int, background: BackgroundTasks, user: str = Depends(require_owner)):
    src = st.storage_dir / "uploads" / f"kb_{kb_id}_upload.zip"
    if not src.exists():
        raise HTTPException(404, "original ZIP not found")
    with db.session() as s:
        kb = s.get(db.KnowledgeBase, kb_id)
        if not kb:
            raise HTTPException(404)
        for model in (db.KnowledgeChunk, db.KnowledgeFile):
            s.query(model).filter(model.kb_id == kb_id).delete()
        kb.status, kb.progress, kb.message = "processing", 0, "re-indexing"
        s.commit()
    background.add_task(ingestion.process, kb_id, src)
    return {"ok": True}


@app.delete("/api/kb/{kb_id}")
def remove_kb(kb_id: int, user: str = Depends(require_owner)):
    ingestion.delete_kb(kb_id)
    return {"ok": True}


# ---------------- agent test + readiness ----------------
class Ask(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    history: list[str] = Field(default_factory=list, max_length=6)


@app.post("/api/agent/ask")
def ask(body: Ask, user: str = Depends(require_owner)):
    with db.session() as s:
        cfg = db.get_config(s)
        s.commit()
    r = Agent().answer(cfg, body.question, body.history)
    return {"reply": r.text, "decision": r.decision, "language": r.language, "sources": r.sources,
            "latency_ms": r.latency_ms, "detail": r.detail}


class TestQ(BaseModel):
    q: str = Field(..., max_length=500)
    expect: str = Field("answer", pattern="^(answer|fallback|safe)$")
    must_include: list[str] = Field(default_factory=list, max_length=5)


@app.get("/api/readiness/questions")
def get_tests(user: str = Depends(require_owner)):
    return json.loads(TESTS_FILE.read_text(encoding="utf-8")) if TESTS_FILE.exists() else []


@app.put("/api/readiness/questions")
def put_tests(body: list[TestQ], user: str = Depends(require_owner)):
    if len(body) > 50:
        raise HTTPException(400, "max 50 test questions")
    TESTS_FILE.write_text(json.dumps([t.model_dump() for t in body], ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True}


@app.post("/api/readiness/run")
def run_readiness(user: str = Depends(require_owner)):
    tests = json.loads(TESTS_FILE.read_text(encoding="utf-8")) if TESTS_FILE.exists() else []
    return readiness.run(tests)


@app.get("/api/readiness/latest")
def latest_readiness(user: str = Depends(require_owner)):
    with db.session() as s:
        r = s.scalar(select(db.ReadinessRun).order_by(desc(db.ReadinessRun.id)).limit(1))
        return {"at": r.at.isoformat(), **r.report} if r else None


# ---------------- models + logs ----------------
@app.get("/api/models")
def models(user: str = Depends(require_owner)):
    o = Ollama()
    return {"runtime": o.version(), "installed": [{"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 2),
                                                   "family": m.get("details", {}).get("family"),
                                                   "quant": m.get("details", {}).get("quantization_level")}
                                                  for m in o.models()],
            "loaded": [{"name": m["name"], "vram_gb": round(m.get("size_vram", 0) / 1e9, 2)} for m in o.loaded()],
            "config": {"chat": st.chat_model, "embed": st.embed_model, "vision": st.vision_model}}


@app.get("/api/logs")
def logs(user: str = Depends(require_owner)):
    with db.session() as s:
        rows = s.scalars(select(db.AuditLog).order_by(desc(db.AuditLog.id)).limit(200)).all()
        return [{"at": r.at.isoformat(), "actor": r.actor, "action": r.action, "detail": r.detail} for r in rows]


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------- WhatsApp (unofficial linked device) ----------------
from .wa import bridge as wa_bridge  # noqa: E402
from .wa import service as wa_service  # noqa: E402

MAX_EVENT_BYTES = 64 * 1024   # text events only; files are never sent here while media is off
RISK_TEXT = ("I understand that QR / WhatsApp-Web linking is not the official WhatsApp Business API, that WhatsApp may "
             "log out, restrict or ban the linked number, and that I should link a separate test number first.")


@app.on_event("startup")
def _restore_whatsapp() -> None:
    """If a linked session is saved (encrypted), start the bridge so it reconnects without a new QR."""
    if (st.storage_dir / "whatsapp_sessions" / "default" / "creds.enc").exists():
        try:
            wa_bridge.start()
        except wa_bridge.BridgeError as exc:
            logging.getLogger("smartech").error("could not restore WhatsApp session: %s", exc)


def _bridge_auth(request: Request) -> None:
    import hmac
    if not st.bridge_secret or not hmac.compare_digest(request.headers.get("x-bridge-secret", ""), st.bridge_secret):
        raise HTTPException(401)


@app.post("/api/wa/state", include_in_schema=False)
async def wa_state(request: Request):
    _bridge_auth(request)
    b = await request.json()
    with db.session() as s:
        w = s.scalar(select(db.WaSession).limit(1)) or db.WaSession()
        w.status, w.account = str(b.get("status", ""))[:20], str(b.get("account", ""))[:80]
        s.add(w)
        db.audit(s, "system", "wa_state", status=w.status, error=str(b.get("error", ""))[:200])
        s.commit()
    return {"ok": True}


@app.post("/api/wa/event", include_in_schema=False)
async def wa_event(request: Request, background: BackgroundTasks):
    _bridge_auth(request)
    if int(request.headers.get("content-length") or 0) > MAX_EVENT_BYTES:
        raise HTTPException(413, "event too large")          # never parsed, never stored
    raw = await request.body()
    if len(raw) > MAX_EVENT_BYTES:
        raise HTTPException(413, "event too large")
    ev = json.loads(raw)
    ev.pop("media", None)   # media content is never stored in the database
    background.add_task(wa_service.handle_event, ev)
    return {"ok": True}


@app.get("/api/wa/status")
def wa_status(user: str = Depends(require_owner)):
    with db.session() as s:
        consent = s.scalar(select(db.WaConsent).order_by(desc(db.WaConsent.id)).limit(1))
    live = None
    if wa_bridge.running():
        try:
            live = wa_bridge.call("GET", "/status")
        except wa_bridge.BridgeError:
            live = None
    return {"bridge_running": live is not None, "status": live["status"] if live else "disconnected",
            "qr": live.get("qr") if live else None, "account": live.get("account", "") if live else "",
            "error": live.get("lastError", "") if live else "", "risk_accepted": consent is not None,
            "risk_text": RISK_TEXT}


@app.post("/api/wa/accept-risk")
def wa_accept(user: str = Depends(require_owner)):
    with db.session() as s:
        s.add(db.WaConsent(text=RISK_TEXT))
        db.audit(s, "owner", "wa_risk_accepted")
        s.commit()
    return {"ok": True}


@app.post("/api/wa/connect")
def wa_connect(user: str = Depends(require_owner)):
    with db.session() as s:
        last = s.scalar(select(db.ReadinessRun).order_by(desc(db.ReadinessRun.id)).limit(1))
        consent = s.scalar(select(db.WaConsent).limit(1))
    if not (last and last.ready):
        raise HTTPException(409, "Not READY TO START yet: pass the readiness check first")
    if not consent:
        raise HTTPException(409, "Accept the WhatsApp risk notice first")
    try:
        wa_bridge.start()
        wa_bridge.call("POST", "/connect")
    except wa_bridge.BridgeError as exc:
        raise HTTPException(502, str(exc))
    return {"ok": True}


@app.post("/api/wa/disconnect")
def wa_disconnect(user: str = Depends(require_owner)):
    if wa_bridge.running():
        wa_bridge.call("POST", "/disconnect")
    return {"ok": True}


@app.post("/api/wa/logout")
def wa_logout(user: str = Depends(require_owner)):
    """Logs the linked device out and deletes the local encrypted session."""
    import shutil
    if wa_bridge.running():
        try:
            wa_bridge.call("POST", "/logout")
        except wa_bridge.BridgeError:
            pass
    shutil.rmtree(st.storage_dir / "whatsapp_sessions" / "default", ignore_errors=True)
    with db.session() as s:
        db.audit(s, "owner", "wa_session_deleted")
        s.commit()
    return {"ok": True}


class AutomationIn(BaseModel):
    enabled: bool


@app.put("/api/automation")
def set_automation(body: AutomationIn, user: str = Depends(require_owner)):
    with db.session() as s:
        cfg = db.get_config(s)
        cfg.auto_reply = body.enabled
        db.audit(s, "owner", "automation", enabled=body.enabled)
        s.commit()
    return {"ok": True}


# contacts (max 5 approved)
class ContactIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    number: str = Field(..., min_length=8, max_length=20)


class ContactPatch(BaseModel):
    automation: bool | None = None
    manual_override: bool | None = None
    blocked: bool | None = None


def _contact_out(c: db.Contact, conv: db.Conversation | None, last: db.Message | None) -> dict:
    return {"id": c.id, "label": c.label, "number": f"+{c.wa_id[:-4]}****" if len(c.wa_id) > 6 else c.wa_id,
            "automation": c.automation, "manual_override": c.manual_override, "blocked": c.blocked,
            "conversation_id": conv.id if conv else None,
            "last_message_at": conv.last_message_at.isoformat() if conv and conv.last_message_at else None,
            "last_text": (last.text or "")[:80] if last else ""}


@app.get("/api/contacts")
def contacts(user: str = Depends(require_owner)):
    with db.session() as s:
        out = []
        for c in s.scalars(select(db.Contact).order_by(db.Contact.id)).all():
            conv = s.scalar(select(db.Conversation).where(db.Conversation.contact_id == c.id))
            last = s.scalar(select(db.Message).where(db.Message.conversation_id == conv.id)
                            .order_by(desc(db.Message.id)).limit(1)) if conv else None
            out.append(_contact_out(c, conv, last))
        return out


@app.post("/api/contacts")
def add_contact(body: ContactIn, user: str = Depends(require_owner)):
    num = wa_service.digits(body.number)
    if len(num) < 8:
        raise HTTPException(400, "enter the number with country code")
    with db.session() as s:
        if (s.scalar(select(func.count(db.Contact.id))) or 0) >= st.max_contacts:
            raise HTTPException(409, f"Phase 1 allows {st.max_contacts} approved contacts")
        if s.scalar(select(db.Contact).where(db.Contact.wa_id == num)):
            raise HTTPException(409, "contact already approved")
        s.add(db.Contact(label=body.label, wa_id=num))
        db.audit(s, "owner", "contact_added", contact=wa_service.mask(num))
        s.commit()
    return {"ok": True}


@app.patch("/api/contacts/{cid}")
def patch_contact(cid: int, body: ContactPatch, user: str = Depends(require_owner)):
    with db.session() as s:
        c = s.get(db.Contact, cid)
        if not c:
            raise HTTPException(404)
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(c, k, v)
        db.audit(s, "owner", "contact_updated", contact=wa_service.mask(c.wa_id), **body.model_dump(exclude_none=True))
        s.commit()
    return {"ok": True}


@app.delete("/api/contacts/{cid}")
def delete_contact(cid: int, user: str = Depends(require_owner)):
    with db.session() as s:
        c = s.get(db.Contact, cid)
        if c:
            conv = s.scalar(select(db.Conversation).where(db.Conversation.contact_id == cid))
            if conv:
                s.query(db.Message).filter(db.Message.conversation_id == conv.id).delete()
                s.delete(conv)
            s.delete(c)
            db.audit(s, "owner", "contact_deleted")
            s.commit()
    return {"ok": True}


@app.get("/api/conversations/{conv_id}/messages")
def conv_messages(conv_id: int, user: str = Depends(require_owner)):
    with db.session() as s:
        rows = s.scalars(select(db.Message).where(db.Message.conversation_id == conv_id).order_by(db.Message.id)).all()
        return [{"id": m.id, "direction": m.direction, "type": m.msg_type, "text": m.text, "decision": m.decision,
                 "language": m.language, "sources": m.sources, "status": m.status, "latency_ms": m.latency_ms,
                 "at": m.created_at.isoformat()} for m in rows[-200:]]


class ManualReply(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


@app.post("/api/conversations/{conv_id}/reply")
def manual_reply(conv_id: int, body: ManualReply, user: str = Depends(require_owner)):
    with db.session() as s:
        conv = s.get(db.Conversation, conv_id)
        if not conv:
            raise HTTPException(404)
        last_in = s.scalar(select(db.Message).where(db.Message.conversation_id == conv_id, db.Message.direction == "in",
                                                    db.Message.jid.is_not(None)).order_by(desc(db.Message.id)).limit(1))
        if not last_in:
            raise HTTPException(409, "the customer has not messaged yet; the agent never starts chats")
        contact = s.get(db.Contact, conv.contact_id)
        contact.manual_override = True   # AI stays quiet in this chat until the owner resumes it
        jid = last_in.jid
        s.commit()
    try:
        res = wa_bridge.call("POST", "/send", {"jid": jid, "text": body.text})
    except wa_bridge.BridgeError as exc:
        raise HTTPException(502, str(exc))
    with db.session() as s:
        s.add(db.Message(conversation_id=conv_id, external_id=f"out:{res['id']}" if res.get("id") else None, jid=jid, direction="out", text=body.text,
                         decision="manual", status="sent"))
        db.audit(s, "owner", "manual_reply")
        s.commit()
    return {"ok": True}


# ---------------- dashboard (built React app) ----------------
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(DIST / "index.html")
