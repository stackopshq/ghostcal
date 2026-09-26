"""Téléverser, servir et retirer un avatar.

Le champ « URL de l'avatar » n'a jamais pu fonctionner : aucune route ne recevait de
fichier, et la CSP du frontend (`img-src 'self'`) refuse les images d'ailleurs. On ajoute
donc ce qui manquait plutôt que d'ouvrir la CSP — charger une image tierce fuiterait
l'adresse IP de chaque visiteur, ce qui est un mauvais échange pour cette suite-ci.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from ghostcal.application.avatars import OCTETS_MAX_EN_ENTREE, AvatarRefuse, preparer
from ghostcal.infrastructure.db.auth_repository import SqlAvatarRepository
from ghostcal.infrastructure.db.session import bind_org, bind_user, db_session
from ghostcal.presentation.dashboard_routes import Member, current_member

router = APIRouter(prefix="/v1/me/profile/avatar", tags=["profile"])


@router.post("", status_code=204)
async def televerser(
    fichier: Annotated[UploadFile, File()],
    member: Member = Depends(current_member),
) -> None:
    # On lit **une** fois, borné. `UploadFile` écrit au-delà d'un seuil dans un fichier
    # temporaire, donc lire sans borne laisserait quelqu'un remplir le disque du serveur
    # avec une requête. Un octet de plus que la limite suffit à trancher.
    brut = await fichier.read(OCTETS_MAX_EN_ENTREE + 1)
    try:
        pret = preparer(brut)
    except AvatarRefuse as exc:
        # 422 et non 400 : la requête est bien formée, c'est son contenu qui ne convient
        # pas. Et le message dit pourquoi — « fichier invalide » n'aide personne à
        # choisir une autre image.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with db_session() as session:
        await bind_org(session, member.organization_id)
        # `bind_user` autant que `bind_org`, et c'est ce qui manquait.
        #
        # L'avatar s'écrit dans `users`, que le durcissement RLS (#151) a placé sous
        # `users_update USING (id = current_user_id)`. Sans ce contexte, l'UPDATE ne
        # trouve **aucune ligne** — et un UPDATE qui n'en touche aucune ne lève rien :
        # le téléversement réussirait et n'écrirait rien.
        #
        # C'est le mode de défaillance propre à la RLS : l'écriture ne refuse pas, elle
        # s'applique à l'ensemble vide. Rien dans le journal, rien à l'écran, et un
        # avatar qui ne change pas sans qu'on sache pourquoi.
        await bind_user(session, member.user.id)
        await SqlAvatarRepository(session).enregistrer(
            member.user.id, octets=pret.octets, mime=pret.mime, quand=datetime.now(UTC)
        )


@router.delete("", status_code=204)
async def retirer(member: Member = Depends(current_member)) -> None:
    async with db_session() as session:
        await bind_org(session, member.organization_id)
        # Même raison que pour l'écriture : `users_update` gouverne aussi la remise à
        # zéro des trois colonnes, et sans contexte elle ne toucherait rien.
        await bind_user(session, member.user.id)
        await SqlAvatarRepository(session).effacer(member.user.id)


@router.get("/{user_id}")
async def servir(user_id: uuid.UUID, member: Member = Depends(current_member)) -> Response:
    """L'avatar d'un membre de la même organisation.

    Le dépôt filtre lui-même l'organisation : un avatar est visible de ses collègues, de
    personne d'autre, et cela ne dépend pas de la sécurité au niveau ligne — qui ne
    s'applique pas en production.
    """
    async with db_session() as session:
        await bind_org(session, member.organization_id)
        trouve = await SqlAvatarRepository(session).lire_dans_l_organisation(
            user_id, member.organization_id
        )
    if trouve is None:
        raise HTTPException(status_code=404, detail="aucun avatar")

    octets, mime, modifie = trouve
    return Response(
        content=octets,
        media_type=mime,
        headers={
            # `nosniff` : le navigateur ne doit pas deviner un autre type que celui qu'on
            # déclare. Sans lui, un fichier interprété autrement que comme une image
            # pourrait s'exécuter dans notre origine.
            "X-Content-Type-Options": "nosniff",
            # Privé : l'image n'est visible que des membres de l'organisation, et un cache
            # partagé la servirait à d'autres. L'`ETag` évite de la retélécharger à chaque
            # affichage de profil.
            "Cache-Control": "private, max-age=300",
            "ETag": f'"{modifie.timestamp():.0f}"',
        },
    )
