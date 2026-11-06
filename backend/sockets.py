"""JWT-authenticated Socket.IO for live branch updates.

There is no subscribe event. On connect the server places each socket in a room for its own
user and, for branch staff, their own branch, and only the server decides what is sent where.
A customer therefore has no way to see a branch's queue or anyone else's visit.
"""

from typing import Any

import socketio

from auth_utils import user_from_token
from models.branch import Branch
from models.branch_visit import BranchVisit
from models.user import Role
from services.branch_queue import VisitOut, branch_update

BRANCH_EVENT = "branch:update"  # the staff queue screen: visits, walk-ins, open tickets
VISIT_EVENT = "visit:update"  # a customer's own visit changed (arrived, valued, ...)

sio = socketio.AsyncServer(async_mode="asgi")


def user_room(user_id: object) -> str:
    return f"user:{user_id}"


def branch_room(branch_id: object) -> str:
    return f"branch:{branch_id}"


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: Any = None) -> None:
    token = auth.get("token") if isinstance(auth, dict) else None
    user = await user_from_token(token) if isinstance(token, str) else None
    if user is None:
        raise socketio.exceptions.ConnectionRefusedError("unauthorized")
    await sio.enter_room(sid, user_room(user.id))
    if user.role == Role.STAFF and user.branch_id is not None:
        await sio.enter_room(sid, branch_room(user.branch_id))


async def broadcast_branch(branch: Branch, visit: BranchVisit | None = None) -> None:
    """Push the branch's day to its staff; and, if a visit changed, to that visit's customer."""
    update = await branch_update(branch)
    await sio.emit(BRANCH_EVENT, update.model_dump(mode="json"), room=branch_room(branch.id))
    if visit is not None and visit.customer_id is not None:
        view = VisitOut.build(visit, branch.name)
        await sio.emit(VISIT_EVENT, view.model_dump(mode="json"), room=user_room(visit.customer_id))
