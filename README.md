<div align="center">

# 🪙 Gold Loan Assistant

### A voice-first assistant for a gold-loan company

*Estimate a gold loan, book a branch visit for valuation, check a loan account, and get help, by voice or text in **English, Hindi, Kannada, Malayalam and Tamil**.*

<br/>

![Scope](https://img.shields.io/badge/scope-client%20demo-blue?style=for-the-badge)
![Data](https://img.shields.io/badge/data-mock%20only-orange?style=for-the-badge)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)
![MongoDB](https://img.shields.io/badge/MongoDB-47A248?style=flat-square&logo=mongodb&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat-square&logo=redis&logoColor=white)
![Socket.IO](https://img.shields.io/badge/Socket.IO-010101?style=flat-square&logo=socketdotio&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-8E75B2?style=flat-square&logo=googlegemini&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)

<br/>

<!-- DEMO-GIF -->

[Features](#-features) •
[The assistant](#-the-assistant) •
[Guardrails](#-financial-safety-guardrails) •
[Architecture](#-architecture) •
[Benchmarks](#-benchmarks) •
[Tech stack](#-tech-stack) •
[Quick start](#-quick-start)

</div>

---

> [!WARNING]
> **Demo system with mock data only.** Every customer, loan, branch and account number here is made up. Never enter a real account number, OTP or PIN.

## 💡 The problem

A gold-loan customer's questions are mostly the same few: *how much can I get for my gold, where is the nearest branch, how much do I owe and when, what do I need to bring.* Today they are answered on the phone or at the counter, often in the customer's own language.

This assistant answers them by voice or text in five Indian languages, books the branch visit that turns an enquiry into a loan, and hands branch staff a live queue. It never asks for an OTP, never promises a loan amount, and never gives investment advice, and those rules are enforced in code and tested in CI.

---

## ✨ Features

### 👤 Customer
- **Log in with a one-time code** (mocked: the demo shows the code on screen). The assistant itself never asks for it.
- **Loan estimate:** grams (or pavan) × purity (18/22/24 carat) × today's gold rate × the loan-to-value limit, always as a **range**, with interest schemes and their monthly interest.
- **Book a gold valuation visit:** city, day, slot, then an explicit confirmation.
- **My loans:** outstanding amount, interest due and its date, maturity, the top-up the gold supports, and reminders: interest due soon or overdue, maturity soon, and a **warning before an auction notice**. Accounts are only ever shown as *ending 0004*.
- **Help:** a complaint or callback request routed to the branch, and a branch finder.
- **The assistant:** a chat panel with a **Speak** button. Text and voice share one conversation.

### 🏦 Branch staff
- **Today at the branch, live:** who is waiting (numbered), today's bookings with **Customer arrived** and **No-show**, walk-ins added by name, and open callbacks and complaints. Every change arrives over Socket.IO.

### 📊 Admin
- **Leads:** estimates given, visits booked after an estimate, and the conversion between them.
- **The assistant:** top intents, language split, how long customers wait (P50/P95), latency per stage, which tier answered, and guardrail activity.
- **Voice credits:** speech-API use against the caps. **Today's gold rate** is set here.

---

## 🤖 The assistant

### Four specialist agents, and one for everything else

| Agent | Handles | Tools |
|---|---|---|
| **Loan calculator** | "Mere paas 30 gram sona hai, kitna loan milega?" | `estimate_loan`, `get_gold_rate` |
| **Branch visit** | book or cancel a valuation slot | `find_branches`, `find_valuation_slots`, `book_visit`, `list_my_visits`, `cancel_visit` |
| **Account** | outstanding, interest due, maturity, renewal, top-up | `get_my_loans` |
| **Help** | documents, timings, gold rate, part-payment, complaints and callbacks | `get_faq`, `get_gold_rate`, `find_branches`, `raise_ticket` |
| General | greetings, thanks, anything else | — |

- **Routing** happens locally first: keyword rules, then a multilingual sentence-embedding model. Only a message neither is sure about is sent to Gemini to classify.
- **Two-step confirmation.** `book_visit`, `cancel_visit` and `raise_ticket` change nothing the first time they are called. The change goes through only when the customer says yes in the *next* turn, so a model can never book in the same breath as it suggests it.
- **The customer's identity never comes from the model.** Every tool takes it from the verified session, and any ID a model passes is dropped.
- **The headline estimate needs no model at all.** Grams, pavan, tola and carat are read from the customer's words (digits or common English and Hindi number words), and the reply is written in the customer's own language from templates. With Gemini down, the demo still works.

### Voice

A cascaded pipeline: **Silero VAD → Gnani speech-to-text → the same agents and guardrails as text → Gnani text-to-speech**, sentence by sentence, with **barge-in** (speak over the reply to interrupt it).

- One Gnani voice speaks all five languages, and reads ₹2,47,500 as "two lakh forty-seven thousand five hundred rupees".
- The estimate disclaimer is **spoken**, not only shown.
- **Credits are protected.** One request at a time (the key allows one), repeated sentences replayed from memory for free, optional hard caps, and every call stopped the moment the provider reports no credit left. Past a cap, voice turns carry on as text.

### Failover

```
Redis cache  →  Gemini  →  Ollama (local, optional)  →  rule-based replies
```

Each model sits behind a circuit breaker: after a few failures in a row it is skipped for a minute, so an exhausted quota does not cost every turn a wasted wait. Only answers that are the same for every customer (documents, timings, today's gold rate) are cached, keyed on a fingerprint of the facts, so a new gold rate retires every cached rate answer. Nothing about a customer is ever cached.

---

## 🛡 Financial safety guardrails

Checked on what the customer says **and** on what the assistant says, whichever agent or model wrote it. A reply that breaks a rule is replaced whole, never edited. They run as **their own required CI job**.

| Rule | How it is enforced |
|---|---|
| Never ask for an OTP, PIN, CVV or password | A customer who tries to share one gets *"Muthoot will never ask for your OTP…"*; **the model never sees the message**, and the digits are redacted before anything is stored. Replies asking for a secret are blocked. |
| Never promise approval or a final amount | Estimates are always a range plus the disclaimer, shown and spoken. "Your loan is approved", "you will get ₹X" and the like are blocked. |
| No investment advice | "Should I buy gold now?" gets a polite refusal before any model is asked; advice in a reply is blocked. |
| Mask personal data | Account numbers leave the server as the last four digits only; mobile numbers are masked in every screen, live update and reply. |
| Account details only after verification | Only a customer logged in with the OTP can see loans, and only their own. Staff and admins cannot open loan accounts. |

Warnings, disclaimers and safe fallback replies exist in all five languages.

---

## 🏗 Architecture

```
 Browser (React)  ── REST /api ──────────────┐
   │  ├─ Socket.IO  (live branch queue)       │
   │  └─ WebSocket /ws/voice (mic up, speech down)
   ▼                                          ▼
 FastAPI (one process, also serves the built app)
   ├─ routes: auth · gold · loans · visits · tickets · branches · chat · admin
   ├─ orchestrator: input guardrails → router → agent + tools → output guardrails → memory
   ├─ voice: VAD → Gnani STT → orchestrator → Gnani TTS (sentence by sentence)
   ├─ MongoDB (Beanie): customers, loans, branches, visits, tickets, estimates, turns
   └─ Redis: answer cache · visit-booking workflow tracker
```

---

## ⏱ Benchmarks

All measured on one Windows laptop, against the full Docker Compose stack (app, MongoDB, Redis) with real Gemini and Gnani calls unless noted. Few turns were run to keep the client's speech credits for demos, so a P95 here is close to the slowest turn. The raw results are in [`backend/eval/results/`](backend/eval/results) and [`backend/loadtest/results/`](backend/loadtest/results).

#### Voice: time to first audio (measured)

From the moment the customer stops speaking to the first sound of the reply. Six recorded questions in Hindi, English, Malayalam and Tamil (loan estimate, account, help), streamed over `/ws/voice` exactly as the browser sends them.

| Stage | Baseline P50 | Baseline P95 | **Short first piece P50** | **Short first piece P95** |
|---|---|---|---|---|
| End-of-speech detection (Silero VAD) | 0.55 s | 0.67 s | 0.54 s | 0.58 s |
| Speech to text (Gnani Prisma) | 0.97 s | 2.61 s | 0.65 s | 1.72 s |
| Routing | 0.04 s | 0.14 s | 0.01 s | 0.21 s |
| Assistant (Gemini and tools) | 1.24 s | 3.06 s | 1.35 s | 1.88 s |
| First piece spoken (Gnani Timbre) | 3.97 s | 7.16 s | **1.50 s** | **1.98 s** |
| **Time to first audio** | 7.41 s | 9.93 s | **4.57 s** | **5.66 s** |

**What changed.** Gnani's REST text-to-speech returns a sentence only once all of it is synthesised, and the time grows with its length, so a full estimate sentence of about 90 characters was most of the wait. The pipeline now cuts a long first sentence at a comma or word boundary (about 60 characters) and speaks that piece while the rest is synthesised. Time to first audio fell by about 40%.

**Next step, not yet done:** Gnani also offers streaming TTS (server-sent events and WebSocket), which returns audio as it is made. That should take the first-piece time below a second.

#### Load: 50 customers at once (measured)

[Locust](backend/loadtest/locustfile.py), 50 simulated customers for one minute against the Docker stack, each logging in with the demo OTP and then mixing chat, *My loans* and loan estimates. No model (rule-based answers) and no voice, so nothing is spent.

| Request | Count | Failures | P50 | P95 |
|---|---|---|---|---|
| `POST /api/chat` | 620 | 0 | 320 ms | 980 ms |
| `GET /api/loans/me` | 212 | 0 | 110 ms | 390 ms |
| `POST /api/gold/estimate` | 202 | 0 | 110 ms | 390 ms |
| **All requests** | **1,134** | **0** | 220 ms | 800 ms |

#### Intent routing (measured)

[`backend/eval/run_eval.py`](backend/eval/run_eval.py) on two labelled sets in all five languages. *Accuracy* is the classifier's best guess; *decided locally* is how many turns it was sure enough to route without asking Gemini, and how many of those were right. A confident wrong answer is the costly kind.

| | Dev set (51, written with the rules) | Indirect phrasing (25, few trigger words) |
|---|---|---|
| Keywords only | 100% · decided locally 50/51, all right | 12% · decided locally 1/25, right |
| Keywords + embeddings | 100% · decided locally 51/51, all right | **68%** · decided locally 9/25, 7 right |

Keyword rules alone almost never guess wrong; they hand what they don't recognise to Gemini. The embedding model lifts the best guess on indirect phrasing from 12% to 68%, which matters most when Gemini is unavailable. Its confidence margin was raised from 0.05 to 0.10 after this test, which halved the wrong local decisions (5 to 2) without changing accuracy, so the indirect set is no longer a blind test. CI runs the keyword-only check on the dev set as a regression gate.

---

## 🛠 Tech stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18 · Vite · React Router 6 · socket.io-client · Axios · Recharts |
| **Backend** | Python 3.12 · FastAPI · Uvicorn · Pydantic · python-socketio · slowapi |
| **Database** | MongoDB (Motor + Beanie) |
| **Cache / workflow** | Redis |
| **Auth** | PyJWT · bcrypt (staff) · mock OTP (customers) |
| **LLM** | Gemini (tool calling) · Ollama (optional offline fallback) · rule-based replies |
| **Intent routing** | Keyword rules + a multilingual sentence-transformers model via fastembed (ONNX, local CPU) |
| **Voice** | Silero VAD (onnxruntime) · **Gnani** Prisma speech-to-text · **Gnani** Timbre text-to-speech |
| **Testing** | pytest · mongomock-motor · fakeredis · Vitest · React Testing Library · Locust |
| **Quality** | ruff · mypy · ESLint · Prettier · pre-commit · gitleaks |
| **DevOps** | Docker · Docker Compose · GitHub Actions |

---

## 🚀 Quick start

### Try it now: no Docker or database needed

The whole app against an in-memory database that is already seeded. Everything is lost when you stop it.

```bash
cd frontend && npm ci && npm run build && cd ..

cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -e ".[dev,voice]"
python -m scripts.dev_server
```

Open **http://localhost:8000**.

| Role | Log in with |
|---|---|
| Customer | mobile `9000000201`, then the code shown on screen |
| Branch staff (Kochi) | mobile `9000000101`, password `goldloan-demo-1` |
| Admin | mobile `9000000100`, password `goldloan-demo-1` |

To see the live queue, open the customer in one browser window and the staff member in another, then book a Kochi visit.

Without keys the assistant still runs: it answers from rules, and voice uses stand-ins. Copy `.env.example` to `.env` and add a Gemini key for the model and the client's Gnani key for real speech.

### With Docker Compose

The app with a real MongoDB and Redis. Data is kept in a Docker volume between restarts.

```bash
cp .env.example .env            # set JWT_SECRET, SEED_DEFAULT_PASSWORD and the keys
docker compose up --build -d    # app :8000 · mongo :27017 · redis :6379
docker compose exec app python -m scripts.seed_data
```

`docker compose down` stops everything; add `-v` to also delete the data. Set `APP_PORT=8001` to publish the app on another port.

### Public demo (Render, free)

[`render.yaml`](render.yaml) is a Render Blueprint that deploys the app and a Render Key Value instance (Redis-compatible) together, with MongoDB on Atlas, all on free tiers. The demo data is seeded automatically on the first start.

Render's free instance has 512 MB of memory and a tenth of a CPU. Speech runs on Gnani's servers, so **voice works there too**; only the local embedding model is left out, and routing uses the keyword rules with Gemini for the rest.

| | Demo on Render | Full app (Docker Compose) |
|---|---|---|
| Text chat | Gemini, with cache and rule-based fallbacks | Same, plus the embedding classifier |
| Voice | ✅ Gnani speech, with tighter credit caps for a public link | ✅ |
| Memory used | about 90 MB | about 1 GB |

Checked before deploying, with the same image held to 512 MB and a tenth of a CPU:
- **Start-up took about 3 minutes**, mostly loading Python libraries, and the first two chat answers after it took about 20 s each. After that, answers took about 2 s, and a repeated question 1.8 s from the cache.
- **The free instance sleeps after 15 minutes without visitors**, so open the demo and ask one question a few minutes before showing it.
- Render's free plan has no fixed IP address, so the Atlas IP access list allows `0.0.0.0/0`; the database user's password is what protects it.

### Tests

```bash
cd backend  && pytest                 # pytest -m guardrail for the safety rules alone
cd frontend && npm test
```

---

## 🔐 Secrets

The Gnani key, Gemini key and database URLs live only in `.env`, which git ignores. Nothing logs them, and no error message includes a provider's response body. `.env.example` holds placeholders only.
