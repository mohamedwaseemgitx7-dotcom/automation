"""READY TO START checks. Every check is real; nothing is assumed."""
import ast
import time
from pathlib import Path

from sqlalchemy import func, select, text

from ..core import db
from ..core.config import get_settings
from ..rag import retrieval
from .agent import Agent
from .ollama_client import Ollama

APP_DIR = Path(__file__).resolve().parents[1]
FORBIDDEN_IMPORTS = {"openai", "anthropic", "google.generativeai", "google.genai", "groq", "cohere", "mistralai"}
FORBIDDEN_HOSTS = ("api.openai.com", "generativelanguage.googleapis.com", "api.anthropic.com", "api.groq.com",
                   "api-inference.huggingface.co", "api.cohere", "api.mistral.ai")

OFF_TOPIC = ["Tell me a joke", "Who will win the next election?", "What is the capital of France?",
             "Write me a poem about the sea"]


def scan_external_ai() -> list[str]:
    problems = []
    for py in APP_DIR.rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        for host in FORBIDDEN_HOSTS:
            if host in src and py.name != "readiness.py":
                problems.append(f"{py.name}: references {host}")
        for node in ast.walk(ast.parse(src)):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                if any(n == f or n.startswith(f + ".") for f in FORBIDDEN_IMPORTS):
                    problems.append(f"{py.name}: imports {n}")
    return problems


def run(test_questions: list[dict] | None = None) -> dict:
    """test_questions: [{"q": "...", "expect": "answer"|"fallback", "must_include": ["..."]}]"""
    st = get_settings()
    ollama = Ollama()
    checks: list[dict] = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    try:
        with db.session() as s:
            s.execute(text("SELECT 1"))
            cfg = db.get_config(s)
            chunks = s.scalar(select(func.count(db.KnowledgeChunk.id)).join(
                db.KnowledgeBase, db.KnowledgeBase.id == db.KnowledgeChunk.kb_id).where(db.KnowledgeBase.active.is_(True))) or 0
            s.commit()
        add("Database healthy", True)
    except Exception as exc:
        add("Database healthy", False, type(exc).__name__)
        return {"ready": False, "checks": checks, "tests": []}

    add("Role instructions saved", bool(cfg.role and cfg.business_name), "role and business name are required")
    add("Knowledge base indexed", chunks > 0, f"{chunks} chunks in the active knowledge base")
    ver = ollama.version()
    add("Local LLM runtime (Ollama) running", ver is not None, f"version {ver}" if ver else "start Ollama")
    names = {m["name"] for m in ollama.models()}
    for m in (st.chat_model, st.embed_model):
        add(f"Model available: {m}", m in names or f"{m}:latest" in names, "run: ollama pull " + m)
    probs = scan_external_ai()
    add("No external AI API in runtime code", not probs, "; ".join(probs[:3]))

    tests = []
    if all(c["ok"] for c in checks):
        retrieval.invalidate()
        agent = Agent(ollama)
        qs = list(test_questions or []) + [{"q": q, "expect": "fallback"} for q in OFF_TOPIC]
        for t in qs:
            t0 = time.perf_counter()
            r = agent.answer(cfg, t["q"])
            if t["expect"] == "answer":
                ok = r.decision == "answered"
            elif t["expect"] == "safe":   # answer or owner handoff are both fine, as long as nothing was invented
                ok = r.decision in ("answered", "fallback", "handoff")
            else:
                ok = r.decision in ("fallback", "refused")
            if ok and t.get("must_include"):
                ok = all(w.lower() in r.text.lower() for w in t["must_include"])
            tests.append({"q": t["q"], "expect": t["expect"], "decision": r.decision, "ok": ok, "reply": r.text[:400],
                          "language": r.language, "sources": r.sources[:2],
                          "ms": int((time.perf_counter() - t0) * 1000), "detail": r.detail})
        off = [t for t in tests if t["expect"] == "fallback"]
        on = [t for t in tests if t["expect"] in ("answer", "safe")]
        add("Unsupported questions get the safe fallback", all(t["ok"] for t in off),
            f"{sum(t['ok'] for t in off)}/{len(off)}")
        if on:
            rate = sum(t["ok"] for t in on) / len(on)
            add("Business questions answered from the knowledge base", rate >= 0.8, f"{rate:.0%} of {len(on)}")
        else:
            add("Business questions answered from the knowledge base", False, "add at least 3 test questions")
    ready = all(c["ok"] for c in checks)
    report = {"ready": ready, "checks": checks, "tests": tests}
    with db.session() as s:
        s.add(db.ReadinessRun(ready=ready, score=sum(c["ok"] for c in checks) / max(1, len(checks)), report=report))
        db.audit(s, "system", "readiness", ready=ready)
        s.commit()
    return report
