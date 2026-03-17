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
