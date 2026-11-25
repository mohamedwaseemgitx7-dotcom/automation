"""WhatsApp message handling with a fake agent and fake sender (no real WhatsApp, no real model)."""
from tests.test_phase1 import FakeOllama  # noqa: F401  (sets env + temp DB first)

from sqlalchemy import select

from app.core import db
from app.llm.agent import AgentReply
from app.wa import service

TEST_NUMBER = "60111111111"


class FakeAgent:
    def __init__(self):
        self.calls = 0

    def answer(self, cfg, text, history=None):
        self.calls += 1
        return AgentReply(f"answer to: {text}", "answered", "en", [{"source": "faq.md"}])


import itertools
_ids = itertools.count(1)


def sent_box():
    box = []
    return box, (lambda jid, text: box.append((jid, text)) or {"id": f"wa{next(_ids)}"})


def ev(i, text="do you repair laptops", frm=TEST_NUMBER, kind="text"):
    return {"id": f"m{i}", "jid": f"{frm}@s.whatsapp.net", "from": frm, "type": kind, "text": text}


def setup_module():
    service._presence = lambda *a: None
    service.MAX_PER_MINUTE = 1000   # many test messages arrive within one minute
    with db.session() as s:
        if not s.scalar(select(db.Contact).where(db.Contact.wa_id == TEST_NUMBER)):
            s.add(db.Contact(label="Tester", wa_id=TEST_NUMBER))
        db.get_config(s).auto_reply = True
        s.commit()


def contact():
    with db.session() as s:
        return s.scalar(select(db.Contact).where(db.Contact.wa_id == TEST_NUMBER))


def set_contact(**kw):
    with db.session() as s:
        c = s.scalar(select(db.Contact).where(db.Contact.wa_id == TEST_NUMBER))
        for k, v in kw.items():
            setattr(c, k, v)
        s.commit()


def test_unknown_sender_ignored():
    box, send = sent_box()
    assert service.handle_event(ev(1, frm="60999999999"), FakeAgent(), send) == "unknown_sender"
    assert box == []


def test_reply_goes_to_same_chat_and_duplicate_skipped():
    box, send = sent_box()
    a = FakeAgent()
    assert service.handle_event(ev(2), a, send) == "answered"
    assert box == [(f"{TEST_NUMBER}@s.whatsapp.net", "answer to: do you repair laptops")]
    assert service.handle_event(ev(2), a, send) == "duplicate"
    assert a.calls == 1 and len(box) == 1


def test_pause_manual_and_global_switch():
    box, send = sent_box()
    set_contact(automation=False)
    assert service.handle_event(ev(3), FakeAgent(), send) == "contact_paused"
    set_contact(automation=True, manual_override=True)
    assert service.handle_event(ev(4), FakeAgent(), send) == "manual_mode"
    set_contact(manual_override=False)
    with db.session() as s:
        db.get_config(s).auto_reply = False
        s.commit()
    assert service.handle_event(ev(5), FakeAgent(), send) == "automation_off"
    with db.session() as s:
        db.get_config(s).auto_reply = True
        s.commit()
    assert box == []


def test_non_text_gets_polite_note():
    box, send = sent_box()
    assert service.handle_event(ev(6, text="", kind="sticker"), FakeAgent(), send) == "non_text:sticker"
    assert "text messages" in box[0][1]


def test_blocked_contact():
    box, send = sent_box()
    set_contact(blocked=True)
    assert service.handle_event(ev(7), FakeAgent(), send) == "blocked"
    set_contact(blocked=False)
    assert box == []


def test_conversations_are_separate():
    other = "60122222222"
    with db.session() as s:
        s.add(db.Contact(label="Other", wa_id=other))
        s.commit()
    box, send = sent_box()
    service.handle_event(ev(8, "first contact question"), FakeAgent(), send)
    service.handle_event(ev(9, "second contact question", frm=other), FakeAgent(), send)
    with db.session() as s:
        convs = {c.contact_id: c.id for c in s.scalars(select(db.Conversation)).all()}
        texts = {cid: [m.text for m in s.scalars(select(db.Message).where(db.Message.conversation_id == conv))]
                 for cid, conv in convs.items()}
    joined = [" ".join(t for t in v if t) for v in texts.values()]
    assert sum("first contact question" in j for j in joined) == 1
    assert sum("second contact question" in j for j in joined) == 1
    assert not any("first contact question" in j and "second contact question" in j for j in joined)


def test_big_file_not_read_or_stored():
    box, send = sent_box()
    big = {"id": "big1", "jid": f"{TEST_NUMBER}@s.whatsapp.net", "from": TEST_NUMBER, "type": "document",
           "text": "secret file text that must not be kept", "size": 25 * 1024 * 1024, "too_large": True}
    a = FakeAgent()
    assert service.handle_event(big, a, send) == "file_too_large_discarded"
    assert a.calls == 0 and "too big" in box[0][1]
    with db.session() as s:
        m = s.scalar(select(db.Message).where(db.Message.external_id == "big1"))
        assert m.text is None and m.decision == "file_too_large_discarded"


def test_oversized_rows_are_purged():
    with db.session() as s:
        conv = s.scalar(select(db.Conversation))
        s.add(db.Message(conversation_id=conv.id, direction="in", text="x" * 50_000))
        s.commit()
    assert db.purge_oversized() == 1


def test_bridge_event_size_limit():
    from fastapi.testclient import TestClient
    from app.core.config import get_settings
    from app.main import app
    st = get_settings()
    st.bridge_secret = "b" * 40
    c = TestClient(app)
    r = c.post("/api/wa/event", content=b"{" + b" " * 70_000 + b"}", headers={"x-bridge-secret": st.bridge_secret,
                                                                             "content-type": "application/json"})
    assert r.status_code == 413


def test_burst_gets_one_contact_owner_note():
    num = "60133333333"
    with db.session() as s:
        s.add(db.Contact(label="Burst", wa_id=num))
        s.commit()
    old = service.MAX_PER_MINUTE
    service.MAX_PER_MINUTE = 8
    try:
        box, send = sent_box()
        results = [service.handle_event(ev(1000 + i, f"question {i}", frm=num), FakeAgent(), send) for i in range(12)]
    finally:
        service.MAX_PER_MINUTE = old
    assert results[:8] == ["answered"] * 8
    assert results[8] == "burst_contact_owner" and "contact the owner" in box[8][1]
    assert results[9:] == ["rate_limited"] * 3 and len(box) == 9      # no further replies
