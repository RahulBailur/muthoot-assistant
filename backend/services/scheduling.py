from datetime import date, datetime, time, timedelta

from models.branch import Branch
from models.branch_visit import BranchVisit, VisitStatus
from time_utils import IST, as_utc, ist_day_bounds, now_utc

Slot = tuple[datetime, datetime]  # UTC start, UTC end


def day_slots(branch: Branch, day: date) -> list[Slot]:
    """Every valuation slot the branch's hours define for a branch-local day, booked or not."""
    if day.weekday() not in branch.open_weekdays:
        return []
    step = timedelta(minutes=branch.slot_minutes)
    start = datetime.combine(day, time.fromisoformat(branch.open_time), tzinfo=IST)
    close = datetime.combine(day, time.fromisoformat(branch.close_time), tzinfo=IST)
    slots: list[Slot] = []
    while start + step <= close:
        slots.append((as_utc(start), as_utc(start + step)))
        start += step
    return slots


async def open_slots(branch: Branch, day: date) -> list[Slot]:
    """Future slots on that day that nobody holds."""
    day_start, day_end = ist_day_bounds(day)
    held = await BranchVisit.find(
        BranchVisit.branch_id == branch.id,
        BranchVisit.slot_start >= day_start,
        BranchVisit.slot_start < day_end,
        BranchVisit.status != VisitStatus.CANCELLED,
    ).to_list()
    taken = {as_utc(visit.slot_start) for visit in held}
    now = now_utc()
    return [slot for slot in day_slots(branch, day) if slot[0] > now and slot[0] not in taken]


def bookable_slot(branch: Branch, slot_start: datetime) -> Slot | None:
    """The branch slot starting exactly then, if it exists and is still in the future."""
    start = as_utc(slot_start)
    if start <= now_utc():
        return None
    for slot in day_slots(branch, start.astimezone(IST).date()):
        if slot[0] == start:
            return slot
    return None
