"""Run the 100 customer questions through the REAL local pipeline and write a report.
Usage: .venv\\Scripts\\python scripts\\run_100.py [chat_model]"""
import csv
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core import db  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.llm import guardrails  # noqa: E402
from app.llm.agent import Agent  # noqa: E402
from tests.data.questions_100 import Q  # noqa: E402

st = get_settings()
if len(sys.argv) > 1:
    st.chat_model = sys.argv[1]
db.init()
with db.session() as s:
    cfg = db.get_config(s)
    s.commit()
agent = Agent()
evidence_all = " ".join(p.read_text(encoding="utf-8") for p in (st.storage_dir / "extracted").rglob("*.md"))

rows = []
for i, (cat, q, expect, must) in enumerate(Q, 1):
    t = time.perf_counter()
    r = agent.answer(cfg, q)
    ms = int((time.perf_counter() - t) * 1000)
    reply = r.text
    if expect == "safe":
        ok = r.decision in ("answered", "fallback", "handoff")
    else:
        ok = r.decision == {"answer": "answered"}.get(expect, expect)
    if ok and r.decision == "answered" and must:
        ok = any(m.lower() in reply.lower() for m in must)
    invented = guardrails.unsupported_facts(reply, evidence_all) if r.decision == "answered" else []
    leak = bool(re.search(r"\b(context|knowledge base|as an ai|language model|we are given)\b", reply, re.I))
    if invented or leak:
        ok = False
    rows.append({"id": f"Q{i:03d}", "category": cat, "question": q, "expect": expect, "decision": r.decision,
                 "ok": ok, "language": r.language, "ms": ms, "reply": reply, "invented": invented, "leak": leak,
                 "sources": [x["source"] for x in r.sources][:3], "reason": r.detail.get("reason", "")})
    print(f"{rows[-1]['id']} {'PASS' if ok else 'FAIL'} {r.decision:9} {ms:6} ms | {q[:60]}")

out = ROOT.parent / "reports"
out.mkdir(exist_ok=True)
tag = st.chat_model.replace(":", "_")
(out / f"test100_{tag}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
with open(out / f"test100_{tag}.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
passed = sum(r["ok"] for r in rows)
lat = sorted(r["ms"] for r in rows)
print(f"\nMODEL {st.chat_model}: {passed}/100 passed | invented facts: {sum(bool(r['invented']) for r in rows)} | "
      f"leaks: {sum(r['leak'] for r in rows)} | p50 {lat[49]} ms | p95 {lat[94]} ms")
cats = {}
for r in rows:
    c = cats.setdefault(r["category"], [0, 0])
    c[0] += r["ok"]
    c[1] += 1
print(" ".join(f"{k}:{v[0]}/{v[1]}" for k, v in cats.items()))
