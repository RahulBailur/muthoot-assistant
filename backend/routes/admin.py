from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query

from auth_utils import AdminUser
from config import get_settings
from models.branch import Branch
from models.branch_visit import BranchVisit, VisitStatus
from models.loan_account import LoanAccount, LoanStatus
from models.loan_estimate import LoanEstimate
from models.ticket import Ticket, TicketStatus
from models.user import Role, User
from services import voice_usage
from services.analytics import turn_summary
from services.gnani import out_of_credit
from time_utils import ist_day_bounds, now_utc, today_ist

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
async def stats(admin: AdminUser, days: Annotated[int, Query(ge=1, le=90)] = 7) -> dict[str, Any]:
    """Business summary: today's visits per branch, open tickets, and leads (estimates
    that turned into booked visits) over the last `days`. Counts only, no personal data."""
    day_start, day_end = ist_day_bounds(today_ist())
    since = now_utc() - timedelta(days=days)

    branches = []
    for branch in await Branch.find_all().sort("+city").to_list():
        today = await BranchVisit.find(
            BranchVisit.branch_id == branch.id,
            BranchVisit.slot_start >= day_start,
            BranchVisit.slot_start < day_end,
        ).to_list()
        branches.append(
            {
                "branch_id": str(branch.id),
                "name": branch.name,
                "city": branch.city,
                **{s.value: sum(v.status == s for v in today) for s in VisitStatus},
                "open_tickets": await Ticket.find(
                    Ticket.branch_id == branch.id, Ticket.status != TicketStatus.RESOLVED
                ).count(),
            }
        )

    estimates = await LoanEstimate.find(LoanEstimate.created_at >= since).count()
    leads = await BranchVisit.find(
        BranchVisit.created_at >= since,
        BranchVisit.estimate_id != None,  # noqa: E711
    ).count()
    return {
        "branches": branches,
        "customers": await User.find(User.role == Role.CUSTOMER).count(),
        "active_loans": await LoanAccount.find(LoanAccount.status == LoanStatus.ACTIVE).count(),
        "period_days": days,
        "estimates": estimates,
        "leads": leads,
        "lead_conversion": round(leads / estimates, 3) if estimates else 0.0,
    }


@router.get("/analytics")
async def analytics(
    admin: AdminUser, days: Annotated[int, Query(ge=1, le=90)] = 7
) -> dict[str, Any]:
    """The assistant over the last `days`: top intents, language split, latency per stage,
    which tier answered (the fallback rate), and guardrail activity. Timings and labels only."""
    return await turn_summary(days)


@router.get("/voice-usage")
async def voice_usage_summary(admin: AdminUser) -> dict[str, Any]:
    """How much of the paid speech APIs has been used, against the caps in config."""
    settings = get_settings()
    usage = await voice_usage.current()
    return {
        "stt_requests": usage.stt_requests,
        "stt_seconds": round(usage.stt_seconds, 1),
        "tts_requests": usage.tts_requests,
        "tts_chars": usage.tts_chars,
        "tts_cache_hits": usage.tts_cache_hits,
        "caps": {
            "stt_seconds": settings.voice_max_stt_seconds or None,
            "tts_chars": settings.voice_max_tts_chars or None,
        },
        "out_of_credit": out_of_credit(),
    }
