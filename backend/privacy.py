"""Masking for personal data. Account and phone numbers never leave the backend in full."""


def last4(number: str) -> str:
    return number[-4:]


def mask_phone(phone: str) -> str:
    """9876543210 -> ******3210"""
    return "*" * (len(phone) - 4) + last4(phone)


def mask_account(account_number: str) -> str:
    """123456789012 -> XXXXXXXX9012"""
    return "X" * (len(account_number) - 4) + last4(account_number)
