from beanie import Document

from models.branch import Branch
from models.branch_visit import BranchVisit
from models.conversation_turn import ConversationTurn
from models.gold_rate import GoldRate
from models.loan_account import LoanAccount
from models.loan_estimate import LoanEstimate
from models.otp_challenge import OtpChallenge
from models.pending_action import PendingAction
from models.ticket import Ticket
from models.turn_analytics import TurnAnalytics
from models.user import User
from models.voice_usage import VoiceUsage

DOCUMENT_MODELS: list[type[Document]] = [
    User,
    Branch,
    LoanAccount,
    BranchVisit,
    GoldRate,
    LoanEstimate,
    Ticket,
    OtpChallenge,
    ConversationTurn,
    PendingAction,
    TurnAnalytics,
    VoiceUsage,
]

__all__ = [
    "DOCUMENT_MODELS",
    "Branch",
    "BranchVisit",
    "ConversationTurn",
    "GoldRate",
    "LoanAccount",
    "LoanEstimate",
    "OtpChallenge",
    "PendingAction",
    "Ticket",
    "TurnAnalytics",
    "User",
    "VoiceUsage",
]
