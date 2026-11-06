"""Run the backend with an in-memory database, already seeded. No MongoDB or Docker needed.

For looking at the API while developing (http://localhost:8000/docs). Everything is lost
when the server stops.

    python scripts/dev_server.py
"""

import asyncio
import os

# The in-memory database is only allowed in the test environment, so this is a test-mode server
os.environ["ENVIRONMENT"] = "test"
os.environ["USE_MOCK_DB"] = "true"
os.environ.setdefault("JWT_SECRET", "dev-server-secret-not-for-any-real-deployment")
os.environ.setdefault("SEED_DEFAULT_PASSWORD", "goldloan-demo-1")
os.environ.setdefault("BCRYPT_ROUNDS", "4")
os.environ["REDIS_URL"] = ""

PORT = 8000


async def main() -> None:
    import uvicorn

    from config import get_settings
    from database import init_db
    from main import app
    from scripts.seed_data import ADMIN, CUSTOMERS, STAFF, seed

    await init_db()
    await seed()

    password = get_settings().seed_default_password
    print(f"\nGold Loan Assistant dev server: http://localhost:{PORT}/docs (in-memory, test mode)")
    print(f"  customer  {CUSTOMERS[0][1]}  (log in with the OTP from /api/auth/otp/request)")
    print(f"  staff     {STAFF[0][1]}  password: {password}")
    print(f"  admin     {ADMIN[1]}  password: {password}\n")

    # lifespan is off because the database above is already initialised and seeded
    server = uvicorn.Server(uvicorn.Config(app, port=PORT, lifespan="off"))
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
