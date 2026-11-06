from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import get_settings
from database import close_db, init_db
from rate_limit import limiter
from routes import admin, auth, branches, gold, loans, tickets, visits
from services.visits import BookingError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings()  # fail fast on invalid configuration
    await init_db()
    yield
    close_db()


app = FastAPI(title="Gold Loan Assistant", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]


@app.exception_handler(BookingError)
async def booking_error(request: Request, error: BookingError) -> JSONResponse:
    return JSONResponse({"detail": error.detail}, status_code=error.status_code)


app.include_router(auth.router)
app.include_router(branches.router)
app.include_router(gold.router)
app.include_router(loans.router)
app.include_router(visits.router)
app.include_router(tickets.router)
app.include_router(admin.router)


@app.get("/api/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
