"""Account export endpoint: data portability (GDPR art. 20). See ADR-0006 §5.

The response carries the sealed blobs verbatim — the server cannot open them. The browser holds the
org private key and assembles the final archive (JSON + .ics) from this payload.

The ``AccountExport`` dataclass is used directly as the response model rather than being mirrored
into a parallel set of Pydantic schemas: a second declaration of the same shape would drift, and a
field added to the export but forgotten in the schema is a silently truncated archive — a
portability bug that nothing would catch.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ghostcal.application.export import AccountExport, ExportService, UnknownUser
from ghostcal.infrastructure.db.export_repository import SqlExportRepository
from ghostcal.infrastructure.db.session import db_session
from ghostcal.presentation.auth_routes import CurrentUser

router = APIRouter(prefix="/v1/me/export", tags=["account"])


@router.get("", response_model=AccountExport)
async def export_account(user: CurrentUser) -> AccountExport:
    """Everything the account holds, across every organization it belongs to.

    Sealed fields are named ``*_sealed`` and come out as ciphertext; only the caller's browser can
    open them. No credential is included — no password hash, no token, no CalDAV password, no
    webhook secret.
    """
    async with db_session() as session:
        try:
            return await ExportService(SqlExportRepository(session)).export(user.id)
        except UnknownUser as exc:
            raise HTTPException(status_code=404, detail="unknown user") from exc
