"""Recording security-relevant actions.

The product's central claim is custody: the server holds your calendar and cannot read it, an
admin can rotate a key and revoke a departed member (ADR-0007), and a deleted account is really
gone (ADR-0006). Every one of those is a claim about *what happened*, and until now nothing wrote
down what happened. There was no way to answer "who rotated the key, and when", which is the first
question anyone asks after an incident — and the answer a revocation feature owes its users.

What goes in, and what must not:

- **In**: the action, the actor, the target's identifier, and small structured facts (a role name,
  a count, a reason).
- **Not in**: anything sealed. Event titles, task content and invitee answers are encrypted to keys
  the server does not hold. An audit log that quietly accumulated plaintext would hand back exactly
  what the encryption exists to withhold — and it would do it in the table people copy into a log
  aggregator.
- **Not in**: passwords, tokens, or key material of any kind, in any form.
"""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

logger = logging.getLogger("ghostcal.audit")


class Action:
    """The vocabulary. A closed set, so queries and alerts can rely on the strings."""

    LOGIN_SUCCEEDED = "auth.login.succeeded"
    LOGIN_FAILED = "auth.login.failed"
    PASSWORD_CHANGED = "auth.password.changed"
    SESSIONS_REVOKED = "auth.sessions.revoked"
    # Second facteur. Le nom reprend celui de GhostPass (« mfa ») dans la forme
    # d'ici (`domaine.objet.action_au_passé`) : les mêmes évènements portent le
    # même nom dans les deux journaux de la suite, ce qui est la seule façon
    # d'écrire une alerte qui vaille pour les deux.
    #
    # Qu'on retire un second facteur est au moins aussi intéressant à retracer
    # qu'on l'ajoute : c'est le geste qu'un attaquant installé fait en premier.
    MFA_ENABLED = "auth.mfa.enabled"
    MFA_DISABLED = "auth.mfa.disabled"
    MFA_RECOVERY_CODES_REGENERATED = "auth.mfa.recovery_codes_regenerated"

    MEMBER_INVITED = "org.member.invited"
    MEMBER_ROLE_CHANGED = "org.member.role_changed"
    MEMBER_REMOVED = "org.member.removed"

    ORG_KEY_ROTATED = "org.key.rotated"

    ACCOUNT_DELETED = "account.deleted"
    RETENTION_PURGED = "retention.purged"


class AuditSink(Protocol):
    async def record(
        self,
        *,
        action: str,
        organization_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        target: str | None,
        details: dict[str, object],
    ) -> None: ...


class AuditLog:
    """Records events, and never lets recording one break the thing being recorded."""

    def __init__(self, sink: AuditSink) -> None:
        self._sink = sink

    async def record(
        self,
        action: str,
        *,
        organization_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        target: str | None = None,
        **details: object,
    ) -> None:
        try:
            await self._sink.record(
                action=action,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                target=target,
                details=details,
            )
        except Exception:
            # Deliberate: a failed audit write must not roll back a member removal or a key
            # rotation. Losing the record of an action is bad; leaving the action half-done
            # because we could not write about it is worse. The failure is loud in the log.
            logger.exception("failed to record audit event %s", action)
