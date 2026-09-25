"""L'avatar vit en base, ré-encodé, borné.

Le champ « URL de l'avatar » était **inutilisable**. Mesuré le 2026-09-25 : l'API n'offre
aucune route de téléversement, et la CSP du frontend est `img-src 'self' data: blob:` —
une URL externe est donc acceptée par le serveur et refusée par le navigateur. Il
n'existait aucune valeur qu'un utilisateur pouvait saisir. (Même `data:`, autorisé par la
CSP, ne passait pas : `avatar_url` est plafonné à 2048 caractères.)

Relâcher la CSP aurait été la solution facile et la mauvaise : charger une image hébergée
ailleurs **fuite l'adresse IP de chaque visiteur** vers un tiers, à chaque affichage de
profil. Pour une suite qui vend le chiffrement de bout en bout, c'est un mauvais échange.

─── Pourquoi en base et pas sur disque ───

L'application n'a **aucun volume monté** — `compose.yaml` n'en donne qu'à PostgreSQL et à
Redis. Un avatar sur le disque du conteneur disparaîtrait au premier redéploiement, et ne
serait vu que d'une réplique sur deux.

En base, il est sauvegardé avec le reste, visible de toutes les répliques, et soumis aux
mêmes politiques de sécurité au niveau ligne que la ligne `users` qui le porte. Le coût
est la taille, et elle est bornée : le service ré-encode à 256 Kio au plus.

─── Les trois colonnes ───

`avatar_mime` porte une contrainte plutôt qu'un type libre : ce qui sort d'ici part dans
un en-tête `Content-Type`, et une valeur arbitraire en base deviendrait une valeur
arbitraire dans une réponse HTTP. On ne stocke que ce qu'on est prêt à servir.

`avatar_updated_at` existe pour l'`ETag` : sans lui, chaque affichage de profil
retéléchargerait l'image.

Revision ID: d2e5b71c48a9
Revises: a7d3f81c60e2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d2e5b71c48a9"
down_revision = "a7d3f81c60e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_bytes", sa.LargeBinary(), nullable=True))
    op.add_column("users", sa.Column("avatar_mime", sa.Text(), nullable=True))
    op.add_column(
        "users", sa.Column("avatar_updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Les trois vont ensemble ou pas du tout : une image sans son type ne peut pas être
    # servie, un type sans image n'a rien à décrire. Une contrainte vaut mieux qu'un
    # commentaire — elle, on ne peut pas l'oublier.
    op.create_check_constraint(
        "ck_users_avatar_complet",
        "users",
        "(avatar_bytes IS NULL AND avatar_mime IS NULL AND avatar_updated_at IS NULL)"
        " OR (avatar_bytes IS NOT NULL AND avatar_mime IS NOT NULL"
        " AND avatar_updated_at IS NOT NULL)",
    )
    # Ce qui sort d'ici devient un en-tête `Content-Type`. On restreint à la source.
    op.create_check_constraint(
        "ck_users_avatar_mime",
        "users",
        "avatar_mime IS NULL OR avatar_mime IN ('image/webp', 'image/png')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_avatar_mime", "users", type_="check")
    op.drop_constraint("ck_users_avatar_complet", "users", type_="check")
    op.drop_column("users", "avatar_updated_at")
    op.drop_column("users", "avatar_mime")
    op.drop_column("users", "avatar_bytes")
