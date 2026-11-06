from beanie import Document

from models.branch import Branch
from models.branch_visit import BranchVisit
from models.gold_rate import GoldRate
from models.loan_account import LoanAccount
from models.loan_estimate import LoanEstimate
from models.otp_challenge import OtpChallenge
from models.ticket import Ticket
from models.user import User

DOCUMENT_MODELS: list[type[Document]] = [
    User,
    Branch,
    LoanAccount,
    BranchVisit,
    GoldRate,
    LoanEstimate,
    Ticket,
    OtpChallenge,
]

__all__ = [
    "DOCUMENT_MODELS",
    "Branch",
    "BranchVisit",
    "GoldRate",
    "LoanAccount",
    "LoanEstimate",
    "OtpChallenge",
    "Ticket",
    "User",
]
