"""Load test: many customers using the gold loan assistant by text at once.

Each simulated customer logs in with the demo OTP, then chats in one conversation and now
and then checks their loans, today's gold rate and a loan estimate, with a pause of 1-3 s
between actions.

The app's rate limits are per IP, and every simulated customer comes from this one machine,
so run against the app with the limits raised (and, for the mocked run, no LLM):

    docker compose -f docker-compose.yml -f backend/loadtest/docker-compose.loadtest.yml up -d
    locust -f backend/loadtest/locustfile.py --host http://localhost:8000 \\
        --headless --users 50 --spawn-rate 10 --run-time 2m --csv backend/loadtest/results/run

Add --tags chat (or loans, estimate) to load one kind of request on its own.

At the end it prints which tier answered the chat turns (cache, gemini, rules...).
"""

import random
import secrets
from collections import Counter
from typing import Any

from locust import HttpUser, between, events, tag, task

QUESTIONS = [
    "Mere paas 30 gram sona hai, kitna loan milega?",
    "I have 4 pavan of 22 carat gold, how much loan?",
    "What is my outstanding amount?",
    "When is my interest due date?",
    "What documents do I need?",
    "What is the gold rate today?",
    "Can I do a part payment?",
    "hello",
    "मेरे पास 20 ग्राम सोना है, कितना लोन मिलेगा?",
    "എന്റെ കയ്യിൽ 4 പവൻ സ്വർണമുണ്ട്, എത്ര വായ്പ കിട്ടും?",
    "என்ன ஆவணங்கள் வேண்டும்",
]

answered_by: Counter[str] = Counter()


class Customer(HttpUser):
    wait_time = between(1, 3)

    def on_start(self) -> None:
        # A fresh mobile number each time, so every simulated customer is new
        phone = f"9{secrets.randbelow(10**9):09d}"
        sent = self.client.post(
            "/api/auth/otp/request", json={"phone": phone}, name="/api/auth/otp/request"
        )
        code = sent.json().get("demo_otp", "")
        verified = self.client.post(
            "/api/auth/otp/verify",
            json={"phone": phone, "otp": code, "name": "Load Test Customer"},
            name="/api/auth/otp/verify",
        )
        token = verified.json().get("access_token", "")
        self.client.headers["Authorization"] = f"Bearer {token}"
        self.session_id: str | None = None

    @tag("chat")
    @task(6)
    def chat(self) -> None:
        body: dict[str, Any] = {"message": random.choice(QUESTIONS)}  # noqa: S311 — not security
        if self.session_id:
            body["session_id"] = self.session_id
        with self.client.post("/api/chat", json=body, name="/api/chat", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"HTTP {r.status_code}")
                return
            data = r.json()
            self.session_id = data["session_id"]
            answered_by[data.get("answered_by", "?")] += 1

    @tag("loans")
    @task(2)
    def my_loans(self) -> None:
        self.client.get("/api/loans/me", name="/api/loans/me")

    @tag("estimate")
    @task(2)
    def estimate(self) -> None:
        grams = random.choice([10, 20, 30, 45])  # noqa: S311 — not security
        self.client.post("/api/gold/estimate", json={"grams": grams}, name="/api/gold/estimate")


@events.test_stop.add_listener
def report_tiers(**_: Any) -> None:
    total = sum(answered_by.values())
    if total:
        shares = ", ".join(
            f"{tier} {count / total:.0%}" for tier, count in answered_by.most_common()
        )
        print(f"\nChat turns answered by: {shares} ({total} turns)")
