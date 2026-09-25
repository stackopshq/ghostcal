"""Email-sending port. Implemented by a Brevo or Resend adapter (or a logging adapter in dev)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Attachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


class EmailSender(Protocol):
    """Ask for a message to be sent.

    "Sent" is deliberately vague about when. An implementation may reach the provider before it
    returns, or merely accept the message and hand it to a worker later
    (`infrastructure/email/outbox.py`). Callers inside a database transaction must assume the
    latter and must not depend on delivery having been attempted by the time `send` returns.
    """

    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachments: Sequence[Attachment] | None = None,
    ) -> None: ...
