"""Email-sending port. Implemented by a Resend adapter (or a logging adapter in dev)."""

from __future__ import annotations

from typing import Protocol


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, html: str) -> None: ...
