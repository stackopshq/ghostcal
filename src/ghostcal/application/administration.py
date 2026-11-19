"""Instance administration: who may administer, sign-up open or closed, accounts.

An instance administrator is an address listed in ``GHOSTCAL_ADMIN_EMAILS``. Nothing in the
database makes someone an administrator, so nothing in the view can: to add or remove one, edit the
variable and restart. That is also why an administrator cannot be suspended or erased from the
view (409): two administrators could otherwise lock each other out, and the second one to click
would win.

What the view sees is metadata only: address, dates, second factor, suspension. Calendars, events
and keys are sealed to keys the server does not hold, and nothing here tries to reach them.

Sign-up, in order of precedence:

1. ``GHOSTCAL_REGISTRATION=open|closed`` pins it. The view shows the state, without a button.
2. Otherwise the choice stored from the view (``instance_settings``, key ``registration``).
3. With no choice ever made, open: the behaviour of every instance before this existed.

A stored value that is neither ``open`` nor ``closed`` reads as closed. The environment variable is
checked at startup and stops the server instead (``config.py``); here, at request time, there is
nobody to tell, and failing closed is the safe way to be wrong about a sign-up switch.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ghostcal.application.account import AccountService, CancelledBooking
from ghostcal.application.audit import Action, AuditLog
from ghostcal.application.auth import AuthenticatedUser, AuthRepository, RegistrationGate
from ghostcal.application.ports.clock import Clock

REGISTRATION_KEY = "registration"


class AdministrationError(Exception):
    """Base class for instance administration errors."""


class NotInstanceAdmin(AdministrationError):
    """The caller is not an instance administrator. The routes answer 404, not 403."""


class UnknownAccount(AdministrationError):
    pass


class TargetIsAdmin(AdministrationError):
    """The target is an instance administrator: remove it from GHOSTCAL_ADMIN_EMAILS instead."""


class RegistrationFixed(AdministrationError):
    """GHOSTCAL_REGISTRATION pins sign-up; the view cannot change it."""


@dataclass(frozen=True, slots=True)
class AccountSummary:
    id: uuid.UUID
    email: str
    name: str
    created_at: datetime
    email_verified: bool
    last_login_at: datetime | None
    two_factor_enabled: bool
    suspended_at: datetime | None


@dataclass(frozen=True, slots=True)
class AccountView:
    """An account as the administration view shows it."""

    summary: AccountSummary
    is_admin: bool


@dataclass(frozen=True, slots=True)
class RegistrationStatus:
    open: bool
    # True when GHOSTCAL_REGISTRATION decides: the view must not offer a button.
    fixed: bool


class AdministrationRepository:
    async def list_accounts(self) -> list[AccountSummary]:
        raise NotImplementedError

    async def get_account(self, user_id: uuid.UUID) -> AccountSummary | None:
        raise NotImplementedError

    async def set_suspended(self, user_id: uuid.UUID, suspended_at: datetime | None) -> None:
        raise NotImplementedError

    async def get_setting(self, key: str) -> str | None:
        raise NotImplementedError

    async def set_setting(self, key: str, value: str, now: datetime) -> None:
        raise NotImplementedError


def resolve_registration(
    fixed: Literal["open", "closed"] | None, stored: str | None
) -> RegistrationStatus:
    if fixed is not None:
        return RegistrationStatus(open=fixed == "open", fixed=True)
    if stored is None:
        return RegistrationStatus(open=True, fixed=False)
    return RegistrationStatus(open=stored == "open", fixed=False)


class StoredRegistrationGate(RegistrationGate):
    """The gate the sign-up paths consult: environment first, then the stored choice."""

    def __init__(
        self, repo: AdministrationRepository, fixed: Literal["open", "closed"] | None
    ) -> None:
        self._repo = repo
        self._fixed = fixed

    async def status(self) -> RegistrationStatus:
        stored = None if self._fixed is not None else await self._repo.get_setting(REGISTRATION_KEY)
        return resolve_registration(self._fixed, stored)

    async def is_open(self) -> bool:
        return (await self.status()).open


class AdministrationService:
    def __init__(
        self,
        repo: AdministrationRepository,
        auth_repo: AuthRepository,
        accounts: AccountService,
        audit: AuditLog,
        clock: Clock,
        *,
        admin_emails: Collection[str],
        registration_fixed: Literal["open", "closed"] | None,
    ) -> None:
        self._repo = repo
        self._auth = auth_repo
        self._accounts = accounts
        self._audit = audit
        self._clock = clock
        self._admins = frozenset(e.strip().lower() for e in admin_emails)
        self._gate = StoredRegistrationGate(repo, registration_fixed)
        self._fixed = registration_fixed

    def is_admin_email(self, email: str) -> bool:
        return email.strip().lower() in self._admins

    def require_admin(self, user: AuthenticatedUser) -> None:
        # A verified address only: an unverified account cannot sign in today, but this is the
        # one check that hands out the whole instance, and it should not lean on another one.
        if not user.email_verified or not self.is_admin_email(user.email):
            raise NotInstanceAdmin(str(user.id))

    async def registration(self, actor: AuthenticatedUser) -> RegistrationStatus:
        self.require_admin(actor)
        return await self._gate.status()

    async def set_registration(
        self, actor: AuthenticatedUser, *, open_: bool
    ) -> RegistrationStatus:
        self.require_admin(actor)
        if self._fixed is not None:
            raise RegistrationFixed(self._fixed)
        before = await self._gate.status()
        value = "open" if open_ else "closed"
        await self._repo.set_setting(REGISTRATION_KEY, value, self._clock.now())
        if before.open != open_:
            await self._audit.record(
                Action.REGISTRATION_CHANGED, actor_user_id=actor.id, state=value
            )
        return RegistrationStatus(open=open_, fixed=False)

    async def list_accounts(self, actor: AuthenticatedUser) -> list[AccountView]:
        self.require_admin(actor)
        return [
            AccountView(summary=a, is_admin=self.is_admin_email(a.email))
            for a in await self._repo.list_accounts()
        ]

    async def _target(self, user_id: uuid.UUID) -> AccountSummary:
        account = await self._repo.get_account(user_id)
        if account is None:
            raise UnknownAccount(str(user_id))
        if self.is_admin_email(account.email):
            raise TargetIsAdmin(str(user_id))
        return account

    async def suspend(self, actor: AuthenticatedUser, user_id: uuid.UUID) -> None:
        """Suspend, and end every session at once.

        The access tokens already issued stay signed until they expire, but `current_user` reads
        `suspended_at` on every request, so they stop working on the next one.
        """
        self.require_admin(actor)
        account = await self._target(user_id)
        now = self._clock.now()
        if account.suspended_at is None:
            await self._repo.set_suspended(user_id, now)
        revoked = await self._auth.revoke_all_refresh_tokens(user_id, now)
        await self._audit.record(
            Action.ACCOUNT_SUSPENDED,
            actor_user_id=actor.id,
            target=str(user_id),
            sessions_revoked=revoked,
        )

    async def reactivate(self, actor: AuthenticatedUser, user_id: uuid.UUID) -> None:
        self.require_admin(actor)
        account = await self._target(user_id)
        if account.suspended_at is not None:
            await self._repo.set_suspended(user_id, None)
            await self._audit.record(
                Action.ACCOUNT_REACTIVATED, actor_user_id=actor.id, target=str(user_id)
            )

    async def delete(
        self, actor: AuthenticatedUser, user_id: uuid.UUID, *, email_confirmation: str
    ) -> list[CancelledBooking]:
        """Erase an account and its data, through the same path as a self-service erasure.

        Raises ``ConfirmationMismatch`` and ``SoleOwner`` from ``application/account.py``
        unchanged; the route maps them as the account route does.
        """
        self.require_admin(actor)
        await self._target(user_id)
        cancelled = await self._accounts.delete_for_admin(
            user_id, email_confirmation=email_confirmation, now=self._clock.now()
        )
        # No target: the log keeps that an administrator erased an account, not whose.
        await self._audit.record(
            Action.ACCOUNT_DELETED, actor_user_id=actor.id, by="instance_admin"
        )
        return cancelled
