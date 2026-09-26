"""An ``EmailSender`` that buffers, so the send can happen *after* the transaction commits.

The failure this exists to undo: `POST /v1/auth/register` ran `provision_account`, stored the
zero-knowledge keys, inserted the verification token and then POSTed to Brevo -- all inside the one
transaction the route opens. Brevo answered 401 (the server's egress address was not on its
allow-list), `raise_for_status()` raised, the exception unwound through the route's
``async with db_session()`` and the transaction rolled back. The caller got a 500 and *nothing was
persisted*: `login` then answered 401, and registering the same address again answered 500 rather
than 409. One third party having a bad afternoon took down every sign-up.

Two rules follow, and this class exists to make them hard to break.

**Nothing may be queued while the transaction is still open.** Measured in
`infrastructure/db/session.py`: `db_session()` wraps the whole route body in `session.begin()`, and
the repository never commits on its own -- `provision_account` is one statement inside that
transaction. So the commit lands when the route's ``async with`` block exits, *after* the service
returns. A `.delay()` fired from inside the service would race a worker that reads the database
before that commit is visible: it would mail a token no row backs yet, or mail an account that the
rollback is about to erase. Hence `send()` only appends; `hand_off()` -- called by the route, after
the block -- is what reaches the queue.

**Handing off may not fail the caller.** Replacing a fatal dependency on Brevo with a fatal
dependency on Redis would be no improvement. `hand_off()` therefore swallows, and logs at ERROR so
the failure is on the operator's screen rather than only in the user's empty inbox.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ghostcal.application.ports.email import Attachment

logger = logging.getLogger("ghostcal.email")


@dataclass(frozen=True, slots=True)
class PendingEmail:
    """A message the application asked for, not yet handed to anyone."""

    to: str
    subject: str
    html: str
    attachments: tuple[Attachment, ...] = ()

    @property
    def recipient_domain(self) -> str:
        """The part of the address safe to log.

        The rest is not. Everywhere else in this codebase an operational log line names what
        failed and not for whom (`account_routes.py:90`, for one), and a queue of verification
        emails is a queue of who signed up and when. The domain still answers the question an
        operator actually has at 3am -- is one provider bouncing us, or is it everyone.
        """
        _, _, domain = self.to.rpartition("@")
        return domain or "unknown"


@dataclass(frozen=True, slots=True)
class HandOff:
    """What came of `hand_off()`. Three states, not two: some may go and some may not."""

    queued: int = 0
    dropped: int = 0

    @property
    def complete(self) -> bool:
        return self.dropped == 0


@dataclass(slots=True)
class DeferredEmailSender:
    """Collect messages now; give them to `dispatch` when the caller says the write is durable.

    Satisfies the `EmailSender` port, so application services keep asking for an email the way
    they always have. What changes is who honours the request and when -- which is an adapter's
    business, not a use case's.
    """

    dispatch: Callable[[PendingEmail], None]
    _pending: list[PendingEmail] = field(default_factory=list)

    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        attachments: Sequence[Attachment] | None = None,
    ) -> None:
        self._pending.append(
            PendingEmail(to=to, subject=subject, html=html, attachments=tuple(attachments or ()))
        )

    @property
    def pending(self) -> tuple[PendingEmail, ...]:
        """What is buffered. For tests and for asserting the queue was not jumped."""
        return tuple(self._pending)

    def hand_off(self) -> HandOff:
        """Pass every buffered message on. Call only once the transaction has committed.

        Never raises. A message that cannot be handed over is lost -- there is no outbox table to
        keep it in -- so it is logged at ERROR, which is the only thing standing between a broker
        outage and a silent one. Deliberately not called from a `finally`: a route that raised
        rolled its transaction back, and there is then nothing to write home about.
        """
        messages, self._pending = self._pending, []
        queued = dropped = 0
        for message in messages:
            try:
                self.dispatch(message)
                queued += 1
            except Exception:
                dropped += 1
                # ERROR, not warning: the user is waiting on this mail and will not get it. The
                # request id on this line ties it back to the account that was just created.
                logger.exception(
                    "email could not be queued and is lost: subject=%r recipient_domain=%s",
                    message.subject,
                    message.recipient_domain,
                )
        return HandOff(queued=queued, dropped=dropped)
