from __future__ import annotations

from dataclasses import dataclass


@dataclass
class User:
    user_id: int
    name: str


@dataclass
class Invoice:
    invoice_id: int
    owner: User
    total: float


@dataclass
class AuditEvent:
    actor: User
    action: str


def fixture_user() -> User:
    """Provide a deterministic local constructor call site for integration tests."""
    return User(user_id=0, name="fixture")
