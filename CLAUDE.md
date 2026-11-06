# Gold-Loan Voice Assistant (Muthoot client demo): project brief

Claude Code reads this file automatically at the start of every session in this folder.

## Background
- I (Rahul G Bailur) built **CareFlow**, a voice-first hospital assistant: `C:\Users\Asus\OneDrive\Desktop\HealthcareProject`
  (GitHub: RahulBailur/CareFlow, live demo: https://careflow-uam3.onrender.com).
- After I showed CareFlow to a company, they asked me to build something similar for **Muthoot**.
  Muthoot Finance is a **gold-loan NBFC, not a bank**, so the demo is built around **gold loans**.
- **Keep the same scale and structure as CareFlow.** Reuse its architecture and code patterns
  (read the matching CareFlow files before writing new ones). Keep it simple.
- The company gave its **own STT and TTS API key**.

## Stack (same as CareFlow)
- **Backend:** Python 3.12, FastAPI, Uvicorn, Pydantic + pydantic-settings, Beanie/Motor → MongoDB, Redis
  (cache + workflow tracker), python-socketio, PyJWT + bcrypt, slowapi, httpx/aiohttp.
- **AI:** Gemini (text LLM with tool calling) → Ollama → rule-based failover with a circuit breaker; fastembed intent
  classifier; multi-agent orchestrator.
- **Voice:** cascaded pipeline (Silero VAD → **client STT** → LLM → sentence-chunked **client TTS**) with barge-in.
- **Frontend:** React 18 + Vite, React Router, axios, socket.io-client, Recharts.
- **Quality and deployment:** pytest (+ mongomock-motor, fakeredis), Vitest, ruff, mypy, pre-commit, Locust, Docker
  Compose, GitHub Actions.

## Where things are in CareFlow (copy the patterns from here)
| Concern | CareFlow files |
|---|---|
| App entry, config, DB | `backend/main.py`, `backend/config.py`, `backend/database.py` |
| Models | `backend/models/` (user, appointment, schedule, pending_action, turn_analytics, ...) |
| Routes | `backend/routes/` (auth, appointments, chat, admin, voice_ws, ...) |
| Agents + orchestrator | `backend/agents/` (orchestrator, intent_classifier, intent_data, base, *_agent, guardrails) |
| Tools + two-step confirmation | `backend/tools/` (booking_tools, confirmation, records_tools, support_tools, ...) |
| Failover / LLM / cache | `backend/services/failover.py`, `llm.py`, `redis_client.py`, `analytics.py` |
| STT / TTS provider interface | `backend/services/stt.py`, `backend/services/tts.py` (FallbackTTS) |
| Voice pipeline | `backend/voice/` (cascade_pipeline, vad, audio_utils, timing) |
| Live updates | `backend/sockets.py`, `backend/services/queue.py` |
| Frontend | `frontend/src/` (pages, components, voice, context, api.js) |
| Tests / eval / load test | `backend/tests/`, `backend/eval/`, `backend/loadtest/` |

## Mapping from CareFlow to this project
| CareFlow | This project |
|---|---|
| Patient | **Customer** |
| Doctor | **Branch staff** |
| Admin | **Admin** |
| Booking agent | **Branch visit agent:** book a gold valuation slot at a branch (two-step confirmation) |
| Triage agent | **Loan calculator agent:** grams × purity (18/22/24 carat) × today's gold rate × LTV (loan-to-value) limit → estimate *range* + interest scheme options |
| Records agent | **Account agent:** outstanding amount, interest due, due date, renewal/top-up, after a mock OTP check |
| Support agent | **Help agent:** KYC documents, branch timings/locator, today's gold rate, complaints → ticket + callback request |
| Medical guardrails | **Financial safety guardrails** (below) |
| Doctor live queue | **Branch walk-in / valuation queue** |

## Use cases
**Customer**
1. Gold loan estimate by voice ("Mere paas 30 gram sona hai, kitna loan milega?", Hindi for "I have 30 grams of gold, how much loan can I get?"). This is the headline demo.
2. Book a branch visit for gold valuation (nearest branch + time slot, confirmed before booking).
3. My loan account (after a mock OTP): outstanding amount, next due date, interest due. Account number spoken as the last 4 digits only.
4. Due-date / maturity / renewal reminders, with a warning before an auction notice.
5. FAQ: documents needed, timings, gold rate, how part-payment works.
6. Complaint ticket + callback request routed to branch staff.

**Branch staff:** today's valuation appointments, walk-in queue, a "customer arrived" button, callback requests.

**Admin analytics:** top intents, language split, voice latency (time to first audio), **leads** (estimates that turned into booked visits).

## Guardrails (must have, with tests in CI)
- Never ask for a full OTP, PIN, CVV or password. If a customer tries to share one, warn them: "Muthoot will never ask for your OTP."
- Never promise approval or a final amount. Always say "estimate; final value after valuation at the branch".
- No investment advice ("should I buy or sell gold now?" → polite refusal).
- Mask personal data: account and phone numbers never shown or spoken in full.
- Account details only after verification.

## Languages
English, Hindi, Kannada, plus **Malayalam and Tamil** if the client's STT/TTS supports them (Muthoot is Kerala-based).
Disclaimers and safe fallback replies in every supported language.

## Milestones (one branch per milestone; I open a PR, squash-merge it and say "done")
1. **M1:** Backend core: models (customers, loan accounts, branches, slots, gold rate, tickets), mock-OTP login + JWT, seed data, REST routes, tests.
2. **M2:** Text assistant: four agents + orchestrator + tools + guardrails + failover + cache, tests (including guardrail tests).
3. **M3:** Voice: the client's STT/TTS behind the provider interface, VAD, barge-in, sentence-chunked TTS, latency timing.
4. **M4:** Frontend: customer pages, branch staff queue (live via Socket.IO), admin analytics.
5. **M5:** Benchmarks (latency, load test), Docker, CI, README with a demo GIF, optional free demo deployment.

## Rules
- **Secrets:** the client's STT/TTS key, Gemini key and DB URLs live only in `.env` (git-ignored). Never print,
  log or commit them. Ship a `.env.example` with placeholders. I will not paste secrets in chat.
- **Mock data only.** No real customer data. Gold rate and LTV limit are config values.
- **Git:** never add `Co-Authored-By: Claude` trailers or "Generated with Claude Code" lines to commits or PRs.
  Only commit and push when I ask. Work on a branch, not `main`. Use a new **private** repo, since this is client work.
- Write simple, readable code with the same comment density and naming as CareFlow.

## Decisions (answered 2026-11-06)
1. STT/TTS provider: **Gnani (Vachana APIs)**. One API key (`GNANI_API_KEY` in `.env`), sent as the
   `X-API-Key-ID` header. STT = Prisma (streaming WebSocket, raw PCM); TTS = Timbre (WebSocket or REST).
   Languages: en-IN, hi-IN, kn-IN, **ml-IN, ta-IN** → all five are in scope. Free tier has limited
   credits (5k), so tests and CI always use the mock provider; only manual demo runs hit Gnani.
   Check the current API reference at https://docs.gnani.ai/llms.txt before writing M3.
   Measured 2026-11-06 (scripts/gnani_probe.py): **1 credit = ₹1**; TTS timbre-v3.0 cost 0.07 credits
   for 37 characters (~0.002/char, ~₹1.9 per 1,000 chars). STT per-second cost not read yet (the
   sidebar badge rounds; the Usage page "Credits Consumed" card is exact). Caps in .env:
   VOICE_MAX_TTS_CHARS=200000, VOICE_MAX_STT_SECONDS=18000. Limits that shape M3: running out of
   credit → HTTP 402; free tier allows **1 active request at a time** (429 `RATE_LIMITED`, no
   Retry-After), so TTS sentence chunks must be sent one after another, never in parallel;
   REST STT clips max 30 s.
2. Demo deadline: **as soon as possible**. Keep each milestone lean; the demo path comes first.
3. Repo name: **muthoot-assistant** (private).
