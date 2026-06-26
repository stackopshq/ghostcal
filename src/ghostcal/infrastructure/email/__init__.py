"""Email adapters: Resend (HTTP) and a logging fallback for local dev."""

from ghostcal.infrastructure.email.sender import build_email_sender

__all__ = ["build_email_sender"]
