# Development log – Local AI WhatsApp Agent

Plan: `D:\D drive\Local AI WhatsApp Agent Plan\Local_AI_WhatsApp_Agent_Plan_v3.pdf` (approved 25 Nov 2026).

## Run

```powershell
.\start-agent.ps1                       # starts Ollama + agent, reconnects WhatsApp, loads models, opens dashboard
.\stop-agent.ps1                        # stops agent + WhatsApp (session kept); add -Ollama to stop the AI too
.\run-agent.ps1                         # backend only, in the foreground (debugging)
backend\.venv\Scripts\python -m pytest -q backend\tests
```
Owner login: username `owner`. A random first password is in `backend\.owner-password.txt` (git-ignored).
Change it with `backend\.venv\Scripts\python backend\scripts\set_password.py`.

## 25 Nov 2026 – Phase 0 + Phase 1

### Done (tested)
- Laptop checked: Ryzen 5 6600H, RTX 3050 4 GB, 16 GB RAM, D: 36 GB free.
- Ollama 0.40.2 serves on **127.0.0.1:11434 only**, models stored in `D:\tools\ollama\models`,
  `OLLAMA_MAX_LOADED_MODELS=1`, CUDA detected on the RTX 3050.
- ffmpeg 9.1 (gyan.dev build) in `D:\tools\ffmpeg`.
- Backend (FastAPI): owner login (PBKDF2 600k, signed HttpOnly SameSite=Strict cookie, CSRF double-submit,
  login lockout after 10 failures), security headers, role config API, ZIP upload, readiness API, models, logs.
- Safe ZIP extraction: size/count/ratio limits, path traversal, symlinks, encrypted entries, executables/macros
  blocked, content-type check by magic bytes. Files parsed as data only.
- Parsing: PDF (PyMuPDF), DOCX, XLSX (values only), CSV, TXT, MD. Chunking 180 words with overlap.
- Local embeddings via Ollama `bge-m3`; hybrid retrieval (cosine + BM25, RRF) over the **active** knowledge base only.
- Agent: harmful/handoff/greeting guards → retrieval threshold → Qwen3 with strict prompt (`NO_ANSWER` rule,
  injection stripping) → claim check (prices, phones, emails, times must exist in sources) → length trim.
- Readiness: DB, role, KB indexed, Ollama running, models present, **AST scan for external AI imports/hosts**,
  owner test questions + automatic off-topic questions. READY TO START only if all pass.
- React + TypeScript + Tailwind dashboard: login, empty-state dashboard, role form, ZIP upload with progress and
  per-file status, re-index/delete, test questions, try-the-agent chat, models, logs, settings, dark/light theme.
  WhatsApp and Conversations pages are honest placeholders until Phase 2.
- Tests: 9 backend tests pass (fake local model for determinism). `pip-audit`: no known vulnerabilities.
  `npm audit`: 0. Semgrep (python, security-audit, react): 0 findings.
- Skills: REA skill installed (text only; its unpinned `npx` MCP not installed). Cloudflare security-audit,
  ponytail, SkillSpector already present. RAG-Anything and Edge0 cloned to `D:\tools\skill-review` for evaluation only.

### Phase 2 – WhatsApp adapter (built, not yet linked to a phone)
- `wa-bridge/`: Node sidecar, **baileys 7.0.0-rc14 pinned exact** (official WhiskeySockets package), installed with
  `--ignore-scripts`; only install script would have been protobufjs' version check. `npm audit`: 0.
- Listens on **127.0.0.1:8200 only**, every call needs `BRIDGE_SECRET` (401 without it – tested).
- Session keys stored with **AES-256-GCM** (`WA_SESSION_KEY`); tested: round-trip OK, no plaintext on disk,
  wrong key cannot read the session.
- Live QR (data URL to dashboard, refreshes), reconnect with back-off, logged-out → session deleted,
  1:1 chats only, never reads contacts or history, no send function except reply-to-chat.
- Backend: risk consent record, connect only when READY + consent, disconnect, logout & delete session,
  global automation switch, 5 approved contacts, per-contact pause / block, manual reply → manual mode
  (AI silent in that chat until "Resume AI"), separate conversation per contact.
- Tests: 15 pass (6 new: unknown sender ignored, duplicate skipped, same-chat reply, pause/manual/global off,
  non-text note, blocked contact, conversations kept separate).
- Dashboard: WhatsApp page (risk notice + consent, QR, status, contacts) and Conversations page (history,
  decisions, sources, latency, manual reply, pause/resume).

### Human-like replies + 100-question test (25 Nov, afternoon)
- Benchmark (RTX 3050 4 GB): `qwen3:4b` = **Thinking** edition (always reasons, 25–40 s, leaked reasoning) → replaced
  by `qwen3:4b-instruct` as default. `qwen3:1.7b`: 119 tok/s, ~1.5 s per answer. First load of a model ~15–55 s,
  so models stay loaded (`OLLAMA_KEEP_ALIVE=60m`, `OLLAMA_MAX_LOADED_MODELS=2` for chat + embeddings).
- Bridge: marks message read (blue ticks), shows "typing…" while the model works, sends after a natural pause
  (2–9 s by length), then "paused". Cosmetic only – never blocks a reply. See `docs/WHATSAPP_SAFE_USE.md`.
- Prompt rewritten for a short, warm WhatsApp staff tone; never mentions documents/AI; partial answers allowed
  ("team will confirm the rest"); polite "not covered" answers.
- Role check: when similarity is borderline (< 0.60) the local model answers a strict YES/NO "can this business
  help?" question first (stops "we can help with your homework").
- Found by the test: an internal notes file in the ZIP (`open-items.txt`) leaked "9am–10pm" into answers.
  Knowledge ZIP v2 removes internal notes. Lesson: only customer-facing facts go into the ZIP.
- 100 questions: `backend/tests/data/questions_100.py`, runner `backend/scripts/run_100.py`, reports in `reports/`.
  Baseline 1.7B (old prompt, KB v1): 89/100, 2 invented facts (from the notes file), p50 1.5 s.
- Apify: connector token invalid/missing – website data was collected directly from smartechsynergys.com instead.

### Final 100-question result + READY (25 Nov, evening)
- BGE-M3 now runs on CPU (`num_gpu: 0`) so Qwen stays on the GPU: no model swapping; search ~0.5 s.
- Added: context-aware YES/NO role check, keyword rescue for retrieval, one-emoji limit, hard block on
  invented "we don't offer X" claims (found by reading replies: Q067 screen repair). A stray control character
  had silently disabled that check once – fixed and covered by a unit test.
- **Qwen3 4B Instruct: 94/100, 0 invented facts, 0 leaked reasoning, p50 3.6 s, p95 5.7 s.**
  All 6 misses are safe owner handoffs (Tanglish 1/4, one Malay) or a missing keyword.
  Report: `reports/Smartech_Agent_100_Question_Test.pdf`.
- Readiness supports `safe` expectations; live readiness run → **READY TO START** (all 9 checks OK).
- 16 backend tests pass; frontend builds clean.

### WhatsApp linked + safety limits (25 Nov, night)
- QR scanned: linked account ***3282 (owner's own number – owner accepted the risk). Session restored automatically
  after server restarts (startup hook), no new QR needed.
- **Big files:** bridge reads only the declared file size from the message header; anything over 10 MB is never
  downloaded, never read, never stored (text dropped too). Customer gets one "file too big" note. Media download
  is OFF until Phase 3. Bridge→backend events capped at 64 KB (413 otherwise). Startup purge deletes any message
  row over 4,000 characters.
- **Message bursts:** 8 messages per contact per minute are answered; the 9th gets one "please contact the owner"
  note (owner alerted in Logs); further messages that minute are stored silently – no reply spam.
- 20 backend tests pass.

### Server-ready code (25 Nov, late) – plan: docs/DEPLOYMENT_PLAN_24x7.md
- Hosting decision: Oracle A1 free VM (owner's debit card), public URL via Tailscale Funnel (no domain). Railway / Vercel /
  Cloudflare-without-domain checked and rejected (0.5 GB RAM / no always-on process / random URL).
- `BRIDGE_MODE=external`: on the server the WhatsApp bridge is its own container; bridge host configurable (`BRIDGE_HOST`).
- Laptop node path moved to `.env` (`NODE_EXE`), code default is `node`.
- `/api/health` now checks DB, models, WhatsApp, disk and returns 503 when degraded (status words only). `/api/live` for Docker.
- Postgres driver (`psycopg` 3.3.9), pinned `requirements.txt`, `scripts/copy_sqlite_to_postgres.py` (refuses non-empty target).
- `deploy/`: arm64-ready Dockerfiles (non-root), compose (postgres, ollama, backend, wa-bridge, tailscale funnel,
  nightly AES-encrypted backups), no published ports. Compose file validated; containers not run on the laptop
  (Docker Desktop stores data on C:) – first real run will be on the VM.
- 20 tests pass.

### Outstanding
- Model downloads are slow/unstable on this connection (retrying automatically). Real-model readiness run and
  benchmark table pending until `bge-m3` and `qwen3:4b` finish.
- Phase 2: Baileys adapter (QR), contacts, conversations, manual mode. Needs the test number to link.
- Phase 3: images (Qwen2.5-VL) and voice (faster-whisper + ffmpeg).
- Phase 4: Docker Compose, Oracle VM, Cloudflare Tunnel + Access, backups, monitoring.
- "harvey" repo link still needed.

### Known limitations
- Tamil/Tanglish quality of a 4B model not measured yet.
- Readiness relevance threshold (cosine 0.50) is a first value; tune after the real benchmark.
- Login lockout counter is in memory (resets on restart).
