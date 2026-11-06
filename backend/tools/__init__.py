"""Tools the agents may call.

Who the customer is never comes from the model. Every handler receives a `ToolContext` built
from the verified session, and no tool declares a customer or user ID parameter. If a model
sends one anyway, it is dropped before the handler sees it.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from agents.languages import Language
from models.user import Role, User
from services.llm import ToolSpec
from services.redis_client import get_workflow_tracker
from services.visits import BookingError
from time_utils import IST, as_utc

ToolResult = dict[str, Any]
Handler = Callable[["ToolContext", dict[str, Any]], Awaitable[ToolResult]]

CUSTOMERS_ONLY = {"error": "Only a logged-in customer can do this."}


@dataclass(frozen=True)
class ToolContext:
    user: User  # from the JWT, never from model output
    language: Language = "en"
    # Which conversation and which turn of it: used to hold changes for confirmation
    session_id: str = "no-session"
    turn_id: str = ""

    @property
    def is_customer(self) -> bool:
        """A customer's login is the (mock) OTP check, so account details may be shown."""
        return self.user.role == Role.CUSTOMER


class ToolArgs(BaseModel):
    """Base for tool argument models: anything the tool did not declare is discarded."""

    model_config = ConfigDict(extra="ignore")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Handler

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.parameters)


def schema(
    properties: dict[str, dict[str, Any]], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def local_time(moment: datetime) -> str:
    """How a time is said to a customer: branch-local, e.g. 'Tue 13 Oct, 10:30 AM'."""
    local = as_utc(moment).astimezone(IST)
    return f"{local:%a} {local.day} {local:%b}, {local:%I:%M %p}".replace(", 0", ", ")


async def run_tool(tool: Tool, context: ToolContext, args: dict[str, Any]) -> ToolResult:
    """Run a tool. Refusals and bad arguments come back as data for the model to explain."""
    try:
        result = await tool.handler(context, args)
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
        result = {"error": f"Invalid arguments: {problems}"}
    except BookingError as error:
        result = {"error": error.detail}
    if stage := workflow_stage(tool.name, result):
        await track_booking(context, stage, tool.name)
    return result


# Visit tools move a booking request along; the others do not touch it
_SLOT_TOOLS = frozenset({"find_valuation_slots"})
_CHANGE_TOOLS = frozenset({"book_visit", "cancel_visit"})


def workflow_stage(tool_name: str, result: ToolResult) -> str | None:
    if tool_name not in _SLOT_TOOLS | _CHANGE_TOOLS:
        return None
    if "error" in result:
        return "failed"
    if tool_name in _SLOT_TOOLS:
        return "slot_checked"
    if result.get("needs_confirmation"):
        return "awaiting_confirmation"
    return "confirmed"


async def track_booking(context: ToolContext, stage: str, tool: str = "") -> None:
    await get_workflow_tracker().advance(
        context.user.id, context.session_id, context.turn_id, stage, tool
    )


# What a changing tool returns once it has really done something
OUTCOME_KEYS = ("booked", "cancelled", "ticket_raised")


def outcome_note(tool_name: str, result: ToolResult) -> str | None:
    """A one-line record of what a tool did or proposed, kept in conversation memory."""
    for key in OUTCOME_KEYS:
        if key in result:
            return f"{key} {result[key]['summary']}"
    if result.get("needs_confirmation"):
        return f"awaiting the customer's yes for {tool_name} {result['repeat_with']['arguments']}"
    return None
