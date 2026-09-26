"""Le schéma écrit dans la migration décrit-il bien le modèle que le code utilise ?

Cette vérification n'est pas de la ceinture et des bretelles : sans PostgreSQL
sous la main, la migration du second facteur n'a jamais été **exécutée**, et
rien d'autre ne relirait les deux descriptions l'une contre l'autre. Elle a déjà
servi une fois — elle a attrapé un `updated_at` présent dans la migration et
absent du modèle, une colonne que rien n'aurait jamais écrite.

Elle ne remplace pas un `alembic upgrade head` contre une vraie base : elle
compare des noms de colonnes, pas des types ni des contraintes. C'est le
troisième état assumé — « je n'ai pas pu regarder tout le reste ».
"""

from __future__ import annotations

import re
from pathlib import Path

from ghostcal.infrastructure.db import models

MIGRATION = Path("migrations/versions/b8e2f47a91c3_two_factor_totp.py")


def test_le_modele_et_la_migration_decrivent_les_memes_colonnes() -> None:
    source = MIGRATION.read_text()
    for table, modele in [
        ("user_totp", models.UserTotp),
        ("user_recovery_codes", models.UserRecoveryCode),
    ]:
        bloc = source.split(f'"{table}",', 1)[1].split("op.create_table", 1)[0]
        dans_migration = set(re.findall(r'sa\.Column\(\s*"([a-z_]+)"', bloc))
        dans_modele = {c.name for c in modele.__table__.columns}
        assert dans_migration == dans_modele, (
            f"{table} : {dans_migration ^ dans_modele} d'un côté seulement"
        )


def test_la_migration_accorde_les_droits_au_role_applicatif() -> None:
    """Sans GRANT, les tables existent et l'application reçoit une erreur de droits.

    Elles sont hors RLS comme `users`, mais le rôle applicatif n'hérite d'aucun
    droit sur une table neuve : l'oubli ne se voit qu'au premier appel réel.
    """
    source = MIGRATION.read_text()
    for table in ("user_totp", "user_recovery_codes"):
        assert f"ON {table} TO ghostcal_app" in source
