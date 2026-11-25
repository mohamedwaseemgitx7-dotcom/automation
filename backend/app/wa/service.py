"""Incoming WhatsApp message handling. Order of checks:
approved contact -> not blocked -> duplicate -> rate limit -> automation on (global + contact) ->
not in manual mode -> type supported -> agent (RAG + local LLM + guardrails) -> send -> store."""
import logging
import re
import time
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..core import db
from ..llm.agent import Agent
from ..rag.normalize import to_english
from . import bridge

log = logging.getLogger(__name__)
BURST_LIMIT = 8        # answered normally per contact per minute (owner asked for 5-10)
MAX_PER_MINUTE = BURST_LIMIT   # kept for tests/backward compatibility
BURST_NOTE = ("You've sent quite a few messages at once. Please contact the owner directly - "
              "they will get back to you as soon as possible.")
NON_TEXT = "Thanks! I can read text messages for now. Please type your question."
TOO_LARGE = ("Sorry, that file is too big for me to open (over 10 MB). Please type your question, "
             "or send a smaller photo.")
MAX_FILE_BYTES = 10 * 1024 * 1024


def digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def mask(n: str) -> str:
    return f"***{n[-4:]}" if n else "?"


def get_conversation(s, contact: db.Contact) -> db.Conversation:
    conv = s.scalar(select(db.Conversation).where(db.Conversation.contact_id == contact.id))
    if not conv:
        conv = db.Conversation(contact_id=contact.id)
        s.add(conv)
        s.flush()
    return conv


def _presence(path: str, body: dict) -> None:
    try:
        bridge.call("POST", path, body)
    except bridge.BridgeError:
        pass   # read receipts / typing are cosmetic; never block a reply


def handle_event(ev: dict, agent: Agent | None = None, sender=None, presence=None) -> str:
    """ev from the bridge: id, jid, from, name, type, text, ts. Returns what happened (for tests/logs)."""
    sender = sender or (lambda jid, text: bridge.call("POST", "/send", {"jid": jid, "text": text}))
    t0 = time.perf_counter()
    phone = digits(ev.get("from", ""))
    with db.session() as s:
        contact = s.scalar(select(db.Contact).where(db.Contact.wa_id == phone))
        if contact is None:
            db.audit(s, "system", "ignored_unknown_sender", sender=mask(phone))
            s.commit()
            return "unknown_sender"
        if contact.blocked:
            s.commit()
            return "blocked"
        conv = get_conversation(s, contact)
        too_large = bool(ev.get("too_large")) or int(ev.get("size") or 0) > MAX_FILE_BYTES
        text = "" if too_large else (ev.get("text") or "")[:2000]   # big file: nothing from it is kept
        msg = db.Message(conversation_id=conv.id, external_id=str(ev.get("id"))[:128], jid=str(ev.get("jid", ""))[:80],
                         direction="in", msg_type=ev.get("type", "text"), text=text or None,
                         normalised=to_english(text) if text else None)
        s.add(msg)
        try:
            s.flush()
        except IntegrityError:
            s.rollback()
            return "duplicate"
        conv.last_message_at = db.now()
        recent = s.scalar(select(func.count(db.Message.id)).where(
            db.Message.conversation_id == conv.id, db.Message.direction == "in",
            db.Message.created_at >= db.now() - timedelta(minutes=1))) or 0
        cfg = db.get_config(s)
        reason = None
        burst_note = False
        if recent > MAX_PER_MINUTE + 1:
            reason = "rate_limited"            # already told once in this minute: stay quiet, no spam
        elif recent == MAX_PER_MINUTE + 1:
            burst_note = True                  # first message over the limit: one "contact the owner" note
        elif not cfg.auto_reply:
            reason = "automation_off"
        elif not contact.automation:
            reason = "contact_paused"
        elif contact.manual_override:
            reason = "manual_mode"
        if reason:
            msg.decision, msg.status = reason, "stored"
            s.commit()
            return reason
        history = list(reversed(s.scalars(select(db.Message.text).where(
            db.Message.conversation_id == conv.id, db.Message.direction == "in", db.Message.id != msg.id,
            db.Message.text.is_not(None)).order_by(db.Message.id.desc()).limit(4)).all()))
        jid, conv_id, msg_id = msg.jid, conv.id, msg.id
        s.commit()

    presence = presence or _presence
    presence("/read", {"jid": jid, "id": str(ev.get("id"))})     # blue ticks, like a person opening the chat
    presence("/typing", {"jid": jid})                           # "typing..." while the local model thinks

    if burst_note:
        reply, decision, sources, lang = BURST_NOTE, "burst_contact_owner", [], None
    elif too_large:
        reply, decision, sources, lang = TOO_LARGE, "file_too_large_discarded", [], None
    elif ev.get("type") != "text" or not text:
        reply, decision, sources, lang = NON_TEXT, f"non_text:{ev.get('type')}", [], None
    else:
        r = (agent or Agent()).answer(cfg, text, history)
        reply, decision, sources, lang = r.text, r.decision, r.sources, r.language
    status = "sent"
    try:
        res = sender(jid, reply)
        out_id = res.get("id") if isinstance(res, dict) else None
    except bridge.BridgeError as exc:
        status, out_id = "failed", None
        log.error("send failed to %s: %s", mask(phone), exc)
    latency = int((time.perf_counter() - t0) * 1000)
    with db.session() as s:
        m = s.get(db.Message, msg_id)
        m.decision, m.language, m.sources, m.status, m.latency_ms = decision, lang, sources, "processed", latency
        s.add(db.Message(conversation_id=conv_id, external_id=f"out:{out_id}" if out_id else None, jid=jid, direction="out", text=reply,
                         decision=decision, sources=sources, status=status, latency_ms=latency))
        if decision in ("handoff", "fallback", "burst_contact_owner"):
            db.audit(s, "ai", "owner_attention", contact=mask(phone), decision=decision)
        s.commit()
    return decision
