"""Email-sending port. Implemented by a Resend adapter (or a logging adapter in dev)."""

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
    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachments: Sequence[Attachment] | None = None,
    ) -> None: ...
