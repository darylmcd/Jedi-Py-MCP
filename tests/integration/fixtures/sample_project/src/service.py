from __future__ import annotations

from src.models import AuditEvent, Invoice, User


def build_invoice(user_name: str) -> Invoice:
    user = User(user_id=1, name=user_name)
    invoice = Invoice(invoice_id=99, owner=user, total=12.5)
    return invoice


def audit_login(user_name: str) -> AuditEvent:
    current_user = User(user_id=2, name=user_name)
    return AuditEvent(actor=current_user, action="login")


def broken_total() -> int:
    value: int = "bad"
    return value
