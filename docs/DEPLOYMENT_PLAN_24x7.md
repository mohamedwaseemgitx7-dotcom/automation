# 24x7 deployment plan – Local AI WhatsApp Agent

Goal: the bot keeps answering WhatsApp with the laptop OFF, Claude Code closed and every browser tab closed.
Status: **plan only – nothing created yet.** Written 25 Nov 2026.

## 0. Update – no domain, no accounts, free plans only (owner decision, 25 Nov 2026)

| Free platform | Free plan (checked) | Can it run our bot? | Use |
|---|---|---|---|
| Railway Free | $1 credit/month, 0.5 GB RAM, services sleep when idle | No – the model alone needs 1.6–3.5 GB, and sleeping kills WhatsApp | not used |
| Vercel Hobby | serverless functions, no always-on process, no disk | No – cannot hold Ollama, Postgres or the WhatsApp session | not used (dashboard is served by the VM, simpler and same-origin login) |
| Cloudflare without a domain | only Quick Tunnels: random `trycloudflare.com` URL that changes on every restart, "testing only", no uptime promise | No – not a permanent address | not used until you own a domain |
| **Oracle A1 Always Free** | 2 ARM cores, 12 GB RAM, 200 GB disk | **Yes** – the only free option big enough | runs everything |
| **Tailscale Funnel** (free personal plan) | permanent `https://<name>.<tailnet>.ts.net` URL, HTTPS certificate automatic, no open ports | Yes – replaces Cloudflare Tunnel + domain | public dashboard URL |

Changes to the plan below: Cloudflare Tunnel + Access → **Tailscale Funnel** (+ the app's own login, lockout and CSRF).
Fallback if Funnel misbehaves: free DuckDNS subdomain + Caddy (Let's Encrypt) on port 443.
Later, if you buy a domain (~US$ 10/year), we can switch to Cloudflare Tunnel + Access in one step.
Oracle sign-up needs a card for identity check even on the free tier; Pay-As-You-Go upgrade is still recommended
to stop idle reclamation (stays $0 inside free limits).

## 1. Facts checked first (they change the design)

| Fact | Source | What it means for us |
|---|---|---|
| Oracle Always Free A1 = **2 OCPU + 12 GB RAM total** (cut from 4/24 in Aug 2026; bigger instances were disabled) | Oracle Free Tier docs, Customer Connect reports | Plan for 2 ARM cores, 12 GB. No GPU. |
| Always Free instances are **reclaimed when idle**: 7 days with 95th-percentile CPU, network and (A1) memory all under 20 % | Oracle Always Free docs | A chatbot idles most of the day → real risk of losing the VM. Fix: upgrade the account to Pay-As-You-Go (resources inside the free limits still cost $0). We will **not** fake load to dodge the rule. |
| Cloudflare Workers: 128 MB per isolate | Cloudflare docs | Cannot run Ollama, Postgres or the WhatsApp session. Cloudflare = DNS, Tunnel, Access, HTTPS only. |
| Laptop today: RTX 3050 GPU, 4B answer ≈ 3.6 s | our benchmark | The VM has **no GPU**. Same model on 2 ARM cores will be roughly 10x slower. Must be measured on the VM before choosing the model. |

## 2. Honest speed estimate on Oracle A1 (to be measured, not promised)

| Model | Est. per reply on 2 ARM cores | RAM | Notes |
|---|---|---|---|
| qwen3:4b-instruct (current, 94/100) | ~40–70 s | ~3.5 GB | prompt reading (RAG context) is the slow part |
| qwen3:1.7b (89/100 old prompt) | ~15–25 s | ~1.6 GB | likely the right pick for free hardware |
| bge-m3 embeddings | ~1 s per question | ~1.3 GB | fine |

WhatsApp users accept a short wait (the bot already shows "typing…"), but 60 s is too long.
Decision rule: benchmark both on the VM; use 4B only if p95 < 30 s, else 1.7B + re-run the 100-question test.
If neither is acceptable → paid VM option (section 4), only after you approve the price.

## 3. Target architecture (one VM, Docker Compose)

```
 Customer WhatsApp ──► WhatsApp servers ◄── outbound WebSocket ── [wa-bridge]
                                                                     │ internal network only
 Owner browser ──HTTPS──► Cloudflare (DNS + Access login) ──Tunnel──► [cloudflared] ──► [backend + dashboard]
                                                                                          │        │
                                                                                     [postgres] [ollama]
 Nothing listens on the internet. Only outbound connections. SSH key-only (or SSH via the tunnel).
```

Containers, all `restart: unless-stopped`, all with health checks:
1. `postgres:16` – volume `pgdata`.
2. `ollama/ollama` – volume `ollama-models`, not published, `OLLAMA_KEEP_ALIVE=-1` so the model stays loaded.
3. `backend` – FastAPI + built dashboard; volume `app-storage` (uploads, extracted KB, logs).
4. `wa-bridge` – Node Baileys; volume `wa-session` (AES-encrypted creds). Separate container, no longer spawned by the backend.
5. `cloudflared` – tunnel token from server-side env file.
6. `backup` – nightly `pg_dump` + encrypted session + KB uploads → local backup volume + Oracle Object Storage (free 20 GB), 14 days kept.

Docker itself starts on boot (systemd), so a VM reboot brings everything back without anyone logging in.

## 4. Hosting decision

| Option | CPU / RAM | GPU | Cost | Risk | Verdict |
|---|---|---|---|---|---|
| **Oracle A1, account upgraded to Pay-As-You-Go** | 2 ARM / 12 GB | no | $0 inside free limits (card needed) | capacity "out of host" when creating; slow replies | **Primary** |
| Oracle A1 Always Free (not upgraded) | same | no | $0 | idle reclamation can delete the VM | not for 24x7 |
| Paid ARM/x86 VPS, 8 vCPU / 16 GB class | 8 / 16 GB | no | ≈ US$ 15–30 / month (price to be checked on the day) | ~3x faster replies | fallback if A1 too slow |
| GPU cloud | – | yes | ≥ US$ 100 / month | – | not worth it for this bot |
| Cloudflare Workers / Pages | 128 MB | – | – | cannot hold LLM or session | no – support role only |

One server only. No paid resource is created without your yes on the exact price.

## 5. Code changes before deployment (the app is laptop-shaped today)

Found in the code:
- `config.py`: `node_exe = "D:/node.exe"`, SQLite path in `storage/`, Ollama/bridge on 127.0.0.1.
- `wa/bridge.py`: backend starts Node as a child process (fine on the laptop, wrong in containers).
- `bridge.js`: listens on 127.0.0.1 only, `BACKEND_URL` default 127.0.0.1.
- `/api/health` returns OK without checking the WhatsApp bridge, DB or Ollama in depth.

Changes:
1. `BRIDGE_MODE=external`: backend talks to the bridge container, never spawns it. Bridge binds to the internal Docker network.
2. Postgres via `DATABASE_URL` (add `psycopg`), one-time copy script SQLite → Postgres (config, contacts, KB + embeddings, conversations).
3. Real `/api/health`: DB query, Ollama model loaded, bridge status, disk free. Returns 503 when something is down.
4. Cookie `Secure` flag + trust Cloudflare proxy headers; login lockout stored in DB (survives restarts).
5. Dockerfiles for arm64 (multi-stage: build React, then slim Python image; Node slim for the bridge), non-root users, pinned versions.
6. Alerts: free external uptime monitor (UptimeRobot / Healthchecks.io) watches the health URL and **emails you** if the server, LLM, DB or WhatsApp is down. Only the health path bypasses Cloudflare Access, and it shows status words only, no data.
7. WhatsApp: keep the existing encrypted session, back-off reconnect, duplicate guard; add "disconnected for > 10 min" → health 503 → email.

Images (Qwen2.5-VL) and voice (Whisper) are **not built yet** (Phase 3). On 2 ARM cores they would run one at a time and slowly. Plan: go live with text first, add media after the text bot is stable on the VM.

## 6. Steps and who does what

| # | Step | Who |
|---|---|---|
| 1 | Scan EGM skill with SkillSpector, read SKILL.md, install (design review only, not a runtime part) | me |
| 2 | Code changes in section 5 + Docker Compose; test the whole stack locally in Docker on the laptop | me |
| 3 | Sign in to Oracle Cloud; upgrade to Pay-As-You-Go (card check) | **you** |
| 4 | Create A1 VM (Ubuntu 24.04 arm64, 2 OCPU, 12 GB, ~100 GB disk), SSH key made on D: | me, you approve |
| 5 | Domain on Cloudflare (buy ~US$ 10/yr if none), create Tunnel + Access policy (your email only) | **you** sign in, I configure |
| 6 | Deploy: Docker, Ollama models one at a time (disk/RAM check before each), Postgres, data copy | me |
| 7 | Benchmark models on the VM, pick model, re-run 100 questions | me |
| 8 | Stop the laptop bot. Link WhatsApp on the VM: **scan a fresh QR from the public dashboard** (cleaner than copying session files; the laptop link is then removed in WhatsApp → Linked devices) | **you** scan |
| 9 | Tests: restart backend, restart Docker, reboot VM, WhatsApp reconnect, backup restore on a copy | me |
| 10 | **Laptop-off test**: shut laptop down, message the bot from another phone, open dashboard on mobile data | **you** |
| 11 | Reports (deployment, audit, security, backup/recovery, monitoring, tests, env reference) – no secrets | me |

## 7. What I am deliberately not doing

- **Arena 16-agent tournament**: the hosting choice is decided by hard limits (no GPU, 12 GB, reclamation rule), not opinions; 16 agents would cost a lot of usage to restate this table. Can still run it if you want.
- No Cloudflare Workers hosting, no ngrok, no laptop IPs, no fake CPU load to avoid reclamation, no anti-ban tricks.
- No promise that WhatsApp keeps an unofficial linked device forever. If WhatsApp logs it out, the health check emails you and you re-scan the QR on the dashboard.

## 8. Decisions needed from you

1. Domain: do you already have one on Cloudflare? (not the client's smartechsynergys.com without their OK)
2. Oracle account: exists? OK to upgrade it to Pay-As-You-Go (card check, $0 inside free limits)?
3. If replies are too slow on free hardware: OK to see a paid VPS price, or stay free with the 1.7B model?
4. Arena: skip (recommended) or run in quick mode?
