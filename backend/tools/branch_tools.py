"""Finding branches and today's gold rate: public facts, shared by several agents."""

from typing import Any

from models.branch import Branch
from routes.branches import BranchOut
from services import gold
from services.visits import branches_in_city
from time_utils import today_ist
from tools import Tool, ToolArgs, ToolContext, ToolResult, schema

MAX_BRANCHES = 5


class FindBranchesArgs(ToolArgs):
    city: str | None = None
    pincode: str | None = None


def describe_branch(branch: Branch) -> dict[str, Any]:
    out = BranchOut.from_branch(branch)
    return {
        "branch_id": out.id,
        "name": out.name,
        "city": out.city,
        "address": f"{out.address}, {out.city} {out.pincode}",
        "phone": out.phone,
        "timings": out.timings,
    }


async def find_branches(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    parsed = FindBranchesArgs.model_validate(args)
    if parsed.city:
        branches = await branches_in_city(parsed.city)
    elif parsed.pincode:
        branches = await Branch.find(Branch.pincode == parsed.pincode.strip()).to_list()
    else:
        branches = await Branch.find_all().sort("+city").to_list()
    if not branches:
        cities = sorted({b.city for b in await Branch.find_all().to_list()})
        return {"branches": [], "note": "No branch found there.", "cities_with_branches": cities}
    return {"branches": [describe_branch(b) for b in branches[:MAX_BRANCHES]]}


async def get_gold_rate(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    rate = await gold.current_rate_24k()
    return {
        "date": today_ist().isoformat(),
        "rate_per_gram": {
            f"{carat}_carat": gold.rupees(gold.rate_for_carat(rate, carat)) for carat in gold.CARATS
        },
    }


FIND_BRANCHES = Tool(
    "find_branches",
    "Find branches by city or 6-digit pincode, with address, phone and timings. "
    "With neither, lists all branches.",
    schema(
        {
            "city": {"type": "string", "description": "City name, e.g. Kochi."},
            "pincode": {"type": "string", "description": "6-digit pincode."},
        }
    ),
    find_branches,
)

GET_GOLD_RATE = Tool(
    "get_gold_rate",
    "Today's gold rate per gram for 24, 22 and 18 carat.",
    schema({}),
    get_gold_rate,
)
