from beanie import PydanticObjectId
from fastapi import APIRouter
from pydantic import BaseModel

from models.branch import Branch
from services.visits import branches_in_city, get_branch

router = APIRouter(prefix="/api/branches", tags=["branches"])

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class BranchOut(BaseModel):
    """Public branch info: no login needed."""

    id: str
    code: str
    name: str
    city: str
    address: str
    pincode: str
    phone: str
    timings: str  # e.g. "Mon–Sat 09:30–17:30"

    @classmethod
    def from_branch(cls, branch: Branch) -> "BranchOut":
        days = sorted(branch.open_weekdays)
        if days and days == list(range(days[0], days[-1] + 1)):
            day_text = f"{WEEKDAY_NAMES[days[0]]}–{WEEKDAY_NAMES[days[-1]]}"
        else:
            day_text = ", ".join(WEEKDAY_NAMES[day] for day in days)
        return cls(
            id=str(branch.id),
            code=branch.code,
            name=branch.name,
            city=branch.city,
            address=branch.address,
            pincode=branch.pincode,
            phone=branch.phone,
            timings=f"{day_text} {branch.open_time}–{branch.close_time}",
        )


@router.get("")
async def list_branches(city: str | None = None, pincode: str | None = None) -> list[BranchOut]:
    """Branch locator: all branches, or those in a city or pincode."""
    if city:
        branches = await branches_in_city(city)
    elif pincode:
        branches = await Branch.find(Branch.pincode == pincode.strip()).to_list()
    else:
        branches = await Branch.find_all().sort("+city").to_list()
    return [BranchOut.from_branch(branch) for branch in branches]


@router.get("/{branch_id}")
async def branch_detail(branch_id: PydanticObjectId) -> BranchOut:
    return BranchOut.from_branch(await get_branch(branch_id))
