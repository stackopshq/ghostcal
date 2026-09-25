"""TOTP (RFC 6238), au-dessus de `pyotp`.

Pourquoi une bibliothèque et non trente lignes maison : TOTP *est* court —
un HMAC-SHA1, une troncature dynamique, un base32 — et c'est précisément ce
qui le rend dangereux à écrire soi-même. L'erreur classique (un décalage
d'octet dans la troncature, un base32 qui perd les bits de bourrage) produit
des codes parfaitement plausibles qui ne correspondent à rien, et le test qui
compare notre implémentation à elle-même ne la voit pas.

Les paramètres sont ceux qu'attendent Google Authenticator, Aegis, 1Password et
les autres, et ceux que GhostPass a déjà retenus : SHA-1, six chiffres,
période de trente secondes. Les changer rendrait les codes incompatibles avec
les applications installées, pour un gain nul.
"""

from __future__ import annotations

import hmac
from datetime import datetime

import pyotp

# Tolérance d'horloge, en périodes de part et d'autre de la période courante.
# Une seule : à trente secondes, cela laisse jusqu'à une minute et demie de
# dérive entre le téléphone et le serveur, ce qui couvre le téléphone mal
# synchronisé sans multiplier par cinq le nombre de codes acceptables à un
# instant donné.
WINDOW = 1

DIGITS = 6
PERIOD_SECONDS = 30
ISSUER = "GhostCal"


class PyotpEngine:
    def new_secret(self) -> str:
        return pyotp.random_base32()

    def provisioning_uri(self, secret: str, *, account: str) -> str:
        return self._totp(secret).provisioning_uri(name=account, issuer_name=ISSUER)

    def verify(self, secret: str, code: str, *, at: datetime) -> int | None:
        code = code.strip()
        if len(code) != DIGITS or not code.isdigit():
            return None
        totp = self._totp(secret)
        current = totp.timecode(at)
        matched: int | None = None
        for offset in range(-WINDOW, WINDOW + 1):
            counter = current + offset
            # `compare_digest` plutôt que `==` : la comparaison d'un secret à
            # une valeur fournie par l'appelant ne doit pas fuir par le temps.
            # Et on ne sort pas de la boucle au premier succès, pour que la
            # durée ne dise pas non plus *quelle* période a répondu.
            if hmac.compare_digest(totp.generate_otp(counter), code):
                matched = counter
        return matched

    def _totp(self, secret: str) -> pyotp.TOTP:
        return pyotp.TOTP(secret, digits=DIGITS, interval=PERIOD_SECONDS)
