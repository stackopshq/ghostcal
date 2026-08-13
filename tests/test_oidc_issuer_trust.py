"""Ce qui vaut preuve de possession d'une adresse, et ce qui n'en vaut pas.

Le 2026-08-13, aucune première connexion SSO ne pouvait aboutir sur cette
instance — pour personne. Cloudflare Access n'émet pas `email_verified` (sa
découverte OIDC n'annonce aucun claim), et un claim absent compte comme non
attesté. Le refus était par ailleurs **indiscernable** d'un OIDC volontairement
éteint : la page de connexion se contentait de ne pas montrer son bouton.

Ces tests figent les deux moitiés de la règle. La seconde compte autant que la
première : un drapeau de confiance qui déborderait sur un autre émetteur
transformerait une commodité en faille.
"""

from __future__ import annotations

import pytest

from ghostcal.presentation import auth_routes

ISSUER = "https://stackopshq.cloudflareaccess.com/cdn-cgi/access/sso/oidc/abc123"
AUTRE = "https://accounts.google.com"


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_routes._settings, "oidc_issuer", ISSUER, raising=False)
    monkeypatch.setattr(auth_routes._settings, "oidc_trust_issuer_email", False, raising=False)


def test_un_claim_explicite_suffit() -> None:
    assert auth_routes.email_is_vouched_for({"email_verified": True}, ISSUER) is True


def test_un_claim_absent_ne_vaut_pas_attestation() -> None:
    """Le défaut, et il doit le rester : omettre le claim n'est pas l'affirmer."""
    assert auth_routes.email_is_vouched_for({"email": "clara@stackops.ch"}, ISSUER) is False


@pytest.mark.parametrize("valeur", [False, "true", 1, None])
def test_seul_le_booleen_vrai_compte(valeur: object) -> None:
    """`"true"` est une chaîne, pas une assertion. `1` non plus."""
    assert auth_routes.email_is_vouched_for({"email_verified": valeur}, ISSUER) is False


def test_la_confiance_a_l_emetteur_debloque_le_cas_cloudflare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_routes._settings, "oidc_trust_issuer_email", True, raising=False)
    assert auth_routes.email_is_vouched_for({"email": "clara@stackops.ch"}, ISSUER) is True


def test_la_confiance_ne_deborde_pas_sur_un_autre_emetteur(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La moitié qui protège : une identité venue d'ailleurs n'hérite de rien.

    Sans cette borne, activer le drapeau reviendrait à accepter n'importe quelle
    adresse de n'importe quel émetteur qui se présente — soit exactement ce que
    la vérification existait pour empêcher.
    """
    monkeypatch.setattr(auth_routes._settings, "oidc_trust_issuer_email", True, raising=False)
    assert auth_routes.email_is_vouched_for({"email": "clara@stackops.ch"}, AUTRE) is False


def test_un_emetteur_vide_n_herite_de_rien(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_routes._settings, "oidc_trust_issuer_email", True, raising=False)
    assert auth_routes.email_is_vouched_for({"email": "clara@stackops.ch"}, "") is False
