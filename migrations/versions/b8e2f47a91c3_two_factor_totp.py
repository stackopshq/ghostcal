"""second facteur TOTP et codes de récupération

GhostCal n'avait aucun second facteur : un mot de passe hameçonné ouvrait le
compte, l'agenda et, par la connexion CalDAV, le calendrier externe du membre.
GhostPass en a un depuis longtemps ; deux produits de la même suite qui ne
protègent pas l'accès de la même façon, c'est une surprise pour l'utilisateur
au pire moment.

Deux tables plutôt que des colonnes sur `users`, dans la lignée de
`user_credentials` : l'absence de ligne dit « pas de second facteur », et rien
ne s'ajoute à la table que tout le reste lit.

`user_totp.secret` est chiffré au repos par la couche applicative
(`EncryptedString`, ADR-0002). La colonne est donc du texte ici : le schéma ne
peut pas le dire, et c'est le modèle qui en porte la responsabilité.

`user_recovery_codes` ne garde que des empreintes, comme
`email_verification_tokens` et `password_reset_tokens`. Une base lue ne rend pas
de code utilisable.

Ces tables sont hors RLS, comme `users` et `user_credentials` : elles sont
antérieures à toute organisation et une identité n'appartient pas à un locataire.

Revision ID: b8e2f47a91c3
Revises: a7d3f81c60e2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b8e2f47a91c3"
down_revision = "a7d3f81c60e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_totp",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        # NULL tant que l'utilisateur n'a pas prouvé qu'il a enrôlé son
        # application. Une ligne non confirmée ne garde aucune porte.
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_counter", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_totp_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_totp")),
    )
    op.create_table(
        "user_recovery_codes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_recovery_codes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_recovery_codes")),
        sa.UniqueConstraint("user_id", "code_hash", name="uq_user_recovery_codes_code"),
    )
    op.create_index(
        op.f("ix_user_recovery_codes_user_id"), "user_recovery_codes", ["user_id"], unique=False
    )
    # Le rôle applicatif lit et écrit ces tables comme les autres tables d'identité ;
    # `users` est globale et ne porte pas de RLS, donc celles-ci non plus.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON user_totp TO ghostcal_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON user_recovery_codes TO ghostcal_app")


def downgrade() -> None:
    op.drop_index(op.f("ix_user_recovery_codes_user_id"), table_name="user_recovery_codes")
    op.drop_table("user_recovery_codes")
    op.drop_table("user_totp")
