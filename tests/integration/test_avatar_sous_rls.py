"""L'avatar s'écrit vraiment, sous le rôle applicatif.

Ce fichier existe parce que `tests/test_avatars.py` n'éprouve que la **préparation** de
l'image — redimensionnement, ré-encodage, refus. Rien ne touchait la base, et la route
serait donc partie avec un défaut invisible.

Le défaut, signalé par la session d'infrastructure : l'avatar s'écrit dans `users`, que le
durcissement RLS a placé sous `users_update USING (id = current_user_id)`. Sans ce contexte,
l'UPDATE ne trouve **aucune ligne** — et un UPDATE qui n'en touche aucune **ne lève rien**.

C'est le mode de défaillance propre à la RLS, et le pire de tous : l'écriture ne refuse pas,
elle s'applique à l'ensemble vide. La requête rend 204, le journal est muet, et l'avatar ne
change pas. Personne ne sait pourquoi.

Ces tests tournent sous `ghostcal_app`, qui ne contourne aucune politique. Sous
superutilisateur ils passeraient quoi qu'il arrive : la RLS y est inerte, et ils ne
prouveraient rien.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ghostcal.application.auth import AuthenticatedUser
from ghostcal.infrastructure.db.auth_repository import SqlAvatarRepository
from ghostcal.infrastructure.db.session import bind_org, bind_user, org_session
from ghostcal.presentation.api import create_app
from ghostcal.presentation.dashboard_routes import Member, current_member

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def compte(admin_engine: AsyncEngine) -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    """Une organisation, un membre. Le strict nécessaire pour écrire un avatar."""
    suffix = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as conn:
        org = await conn.scalar(
            text("INSERT INTO organizations (name, slug) VALUES ('Alpha', :s) RETURNING id"),
            {"s": f"alpha-{suffix}"},
        )
        user = await conn.scalar(
            text(
                "INSERT INTO users (email, name, timezone) VALUES (:e, 'Alice', 'UTC') RETURNING id"
            ),
            {"e": f"alice-{suffix}@example.test"},
        )
        await conn.execute(
            text(
                "INSERT INTO memberships (organization_id, user_id, role) VALUES (:o, :u, 'owner')"
            ),
            {"o": org, "u": user},
        )
    yield org, user
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": user})
        await conn.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org})


async def _avatar_en_base(engine: AsyncEngine, user: uuid.UUID) -> tuple[bytes | None, str | None]:
    async with engine.begin() as conn:
        ligne = (
            await conn.execute(
                text("SELECT avatar_bytes, avatar_mime FROM users WHERE id = :u"), {"u": user}
            )
        ).one()
    return ligne[0], ligne[1]


@pytest.mark.asyncio
async def test_l_avatar_est_vraiment_ecrit(
    admin_engine: AsyncEngine, compte: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """Le cas qui manquait : l'écriture touche une ligne, et on va la relire.

    Relue par l'administrateur et non par la session applicative : on veut savoir ce qui
    est **dans la table**, pas ce que la politique de lecture veut bien en montrer. Les
    deux se confondraient si on relisait sous le même contexte.
    """
    org, user = compte
    async with org_session(org) as session:
        await bind_user(session, user)
        await SqlAvatarRepository(session).enregistrer(
            user, octets=b"des-octets-webp", mime="image/webp", quand=datetime.now(UTC)
        )

    octets, mime = await _avatar_en_base(admin_engine, user)
    assert octets == b"des-octets-webp"
    assert mime == "image/webp"


@pytest.mark.asyncio
async def test_sans_contexte_utilisateur_l_ecriture_ne_touche_rien(
    admin_engine: AsyncEngine, compte: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """La démonstration du piège, épinglée pour qu'elle ne se reperde pas.

    Ce test ne vérifie pas une fonctionnalité : il vérifie que **le défaut est réel**. Sans
    `bind_user`, l'UPDATE ne lève pas, ne prévient pas, et n'écrit pas. Si un jour il se met
    à écrire, c'est que la politique a été desserrée — et on veut le savoir.
    """
    org, user = compte
    async with org_session(org) as session:
        # `bind_org` seul, comme la route le faisait avant correction.
        await bind_org(session, org)
        await SqlAvatarRepository(session).enregistrer(
            user, octets=b"ne-devrait-pas-passer", mime="image/webp", quand=datetime.now(UTC)
        )

    octets, _ = await _avatar_en_base(admin_engine, user)
    assert octets is None, "l'écriture a franchi users_update sans contexte utilisateur"


@pytest.mark.asyncio
async def test_le_retrait_touche_vraiment_la_ligne(
    admin_engine: AsyncEngine, compte: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """Le retrait passe par la même politique que l'écriture, donc par le même piège."""
    org, user = compte
    async with org_session(org) as session:
        await bind_user(session, user)
        repo = SqlAvatarRepository(session)
        await repo.enregistrer(
            user, octets=b"a-retirer", mime="image/webp", quand=datetime.now(UTC)
        )

    async with org_session(org) as session:
        await bind_user(session, user)
        await SqlAvatarRepository(session).effacer(user)

    octets, mime = await _avatar_en_base(admin_engine, user)
    assert octets is None
    assert mime is None


def _image_minuscule() -> bytes:
    """Un PNG d'un pixel, que Pillow reconnaît. Le contenu importe peu ; ce qui compte
    est qu'il franchisse la validation pour atteindre l'écriture."""
    from io import BytesIO

    from PIL import Image

    tampon = BytesIO()
    Image.new("RGB", (8, 8), (0, 240, 255)).save(tampon, format="PNG")
    return tampon.getvalue()


@pytest.mark.asyncio
async def test_la_route_pose_le_contexte_et_ecrit(
    admin_engine: AsyncEngine, compte: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """Le test qui couvre **la route**, et non le dépôt.

    Les trois tests ci-dessus appellent `bind_user` eux-mêmes : ils prouvent que la
    politique mord et que le dépôt écrit quand le contexte est posé, mais ils ne diraient
    rien si la route oubliait de le poser. Or c'est exactement ce qu'elle faisait.

    Celui-ci passe par l'application, avec l'authentification remplacée par un double. Si
    quelqu'un retire `bind_user` de `avatar_routes.py`, il devient rouge — et c'est le seul
    de ce fichier à le faire.
    """
    org, user = compte
    membre = Member(
        user=AuthenticatedUser(
            id=user, email="alice@example.test", name="Alice", email_verified=True
        ),
        organization_id=org,
        role="owner",
    )
    app = create_app()
    app.dependency_overrides[current_member] = lambda: membre

    # `AsyncClient` et non `TestClient`, pour la raison qu'explique déjà
    # `test_portal_widgets.py` : `TestClient` monte **sa propre boucle d'évènements**, et
    # le moteur de base est lié à celle du test. Les deux ne se voient pas, et le symptôme
    # est vicieux — le test passe seul et échoue en groupe.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reponse = await client.post(
            "/v1/me/profile/avatar",
            files={"fichier": ("a.png", _image_minuscule(), "image/png")},
        )
    assert reponse.status_code == 204, reponse.text

    octets, mime = await _avatar_en_base(admin_engine, user)
    assert octets is not None, "la route a rendu 204 sans rien écrire"
    assert mime == "image/webp"
