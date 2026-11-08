"""Per-session conversation memory in MongoDB."""

from beanie import PydanticObjectId

from agents.intent_data import Intent
from agents.languages import LANGUAGES, Language
from models.conversation_turn import ConversationTurn
from services.llm import Message

HISTORY_TURNS = 8


async def _latest(user_id: PydanticObjectId, session_id: str, limit: int) -> list[ConversationTurn]:
    return (
        await ConversationTurn.find(
            ConversationTurn.user_id == user_id, ConversationTurn.session_id == session_id
        )
        .sort("-created_at", "-_id")
        .limit(limit)
        .to_list()
    )


async def recent_messages(user_id: PydanticObjectId, session_id: str) -> list[Message]:
    """The last few turns of this user's session, oldest first."""
    turns = await _latest(user_id, session_id, HISTORY_TURNS)
    return [
        Message(turn.role, f"{turn.text}\n[{turn.note}]" if turn.note else turn.text)
        for turn in reversed(turns)
    ]


async def last_intent(user_id: PydanticObjectId, session_id: str) -> Intent | None:
    turns = await _latest(user_id, session_id, 1)
    return Intent(turns[0].intent) if turns else None


async def chosen_language(user_id: PydanticObjectId, session_id: str) -> Language | None:
    """The language the customer asked for earlier in this conversation, if they did."""
    turns = await _latest(user_id, session_id, 1)
    chosen = turns[0].chosen_language if turns else ""
    return chosen if chosen in LANGUAGES else None


async def remember(
    user_id: PydanticObjectId,
    session_id: str,
    user_text: str,
    reply: str,
    intent: Intent,
    note: str = "",
    language: Language | None = None,
) -> None:
    for role, text in (("user", user_text), ("assistant", reply)):
        await ConversationTurn(
            user_id=user_id,
            session_id=session_id,
            role=role,
            text=text,
            intent=intent.value,
            note=note if role == "assistant" else "",
            chosen_language=(language or "") if role == "assistant" else "",
        ).insert()
