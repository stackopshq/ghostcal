"""Hors développement, l'URL du client doit être publique.

Pourquoi ce test existe : le 25 septembre 2026, `cal.ghostsuite.cloud` envoyait des
courriels de vérification pointant vers `http://localhost:3001/verify-email?token=…`.
L'inscription réussissait, le courriel partait, et le lien échouait **chez le
destinataire** — donc aucun compte ne pouvait être validé, et rien côté serveur ne le
disait. Une panne totale et muette, du même genre que celles que ce dépôt chasse
ailleurs : le réglage de développement *fonctionne*, il produit simplement des liens que
seul l'utilisateur voit casser.

Trois liens sortants sont construits depuis ce réglage, pas un seul : la vérification
d'adresse, les invitations d'organisation et la gestion des tâches. Ils cassent ensemble.
"""

from __future__ import annotations

import pytest

from ghostcal.config import Settings


def _reglages(**surcharges: object) -> Settings:
    base: dict[str, object] = {
        "secret_key": "test-secret-key-at-least-32-characters-long",
        "token_encryption_key": "test-encryption-key-at-least-32-chars-long",
        "database_url": "postgresql+asyncpg://t:t@localhost:5432/ghostcal_absent",
        "database_admin_url": "postgresql+asyncpg://t:t@localhost:5432/ghostcal_absent",
        "redis_url": "redis://localhost:6379/0",
    }
    base.update(surcharges)
    return Settings(**base)  # type: ignore[arg-type]


def test_le_developpement_garde_son_localhost() -> None:
    """Le défaut n'est pas la valeur, c'est la valeur *hors* de son contexte."""
    reglages = _reglages(environment="development", frontend_base_url="http://localhost:3001")
    assert reglages.frontend_base_url == "http://localhost:3001"


@pytest.mark.parametrize("environnement", ["production", "staging"])
@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:3001",
        "https://localhost",
        "http://127.0.0.1:3001",
        "http://0.0.0.0:3001",
    ],
)
def test_une_url_locale_est_refusee_hors_developpement(environnement: str, url: str) -> None:
    with pytest.raises(ValueError, match="frontend_base_url"):
        _reglages(environment=environnement, frontend_base_url=url)


def test_une_url_publique_passe() -> None:
    """Le contrôle doit aussi savoir dire oui — sinon il bloque le déploiement correct."""
    reglages = _reglages(environment="production", frontend_base_url="https://cal.ghostsuite.cloud")
    assert reglages.frontend_base_url == "https://cal.ghostsuite.cloud"
