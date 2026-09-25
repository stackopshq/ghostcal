"""Ce qu'on accepte comme avatar, et ce qu'on en fait avant de le garder.

Un téléversement d'image est un point d'entrée hostile par nature : ce qui arrive est
choisi par quelqu'un d'autre. Trois décisions structurent ce module.

─── 1. On ne croit ni l'extension ni le `Content-Type` ───

Les deux sont fournis par le client. Le type réel se lit dans les **octets**, et c'est
Pillow qui le dit en ouvrant le fichier — pas nous en comparant des préfixes, ce qui
raterait les formats dont l'en-tête varie.

Le SVG est refusé **explicitement**, et pas par oubli : un SVG est un document XML qui
peut porter du script. Servi depuis la même origine que l'application, il exécuterait ce
script dans le contexte de la session. Pillow ne l'ouvre pas, donc il tombe naturellement
— mais on ne compte pas sur un effet de bord pour une propriété de sécurité.

─── 2. On ré-encode toujours, même une image déjà valide ───

Ré-encoder coûte du temps de calcul et apporte deux choses qu'aucune validation ne donne :

* **les métadonnées disparaissent.** Une photo prise au téléphone porte souvent ses
  coordonnées GPS en EXIF. Servir cet avatar à toute une organisation révélerait où la
  photo a été prise. Pour une suite qui vend la confidentialité, ce serait un défaut
  embarrassant — et invisible, puisque l'image s'affiche normalement.
* **les fichiers polyglottes meurent.** Un fichier valide à la fois comme image et comme
  autre chose ne survit pas à un décodage suivi d'un ré-encodage : ce qui ressort est ce
  que Pillow a compris, et rien d'autre.

─── 3. Trois bornes, pas une ───

* à l'entrée, les octets reçus — pour ne pas décoder un fichier énorme ;
* les **dimensions**, avant le redimensionnement — une image de 50 000 sur 50 000 pixels
  tient dans quelques kilo-octets compressés et demande des gigaoctets une fois décodée.
  C'est la bombe de décompression, et la borne d'entrée ne l'arrête pas ;
* à la sortie, le résultat — au cas où le ré-encodage produirait plus gros que prévu.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError

# 2 Mio à l'entrée : au-delà, c'est une photo qu'on n'a pas besoin de recevoir entière
# pour en faire une vignette de 512 pixels.
OCTETS_MAX_EN_ENTREE = 2 * 1024 * 1024

# Pillow avertit au-delà de ~89 Mpx ; on tranche bien avant. Une bombe de décompression
# passe la borne d'entrée sans peine — quelques kilo-octets compressés, des gigaoctets une
# fois décodés — et c'est ici qu'elle doit mourir.
PIXELS_MAX = 50_000_000

COTE_MAX = 512
OCTETS_MAX_EN_SORTIE = 256 * 1024

# Ce que Pillow doit avoir reconnu. `SVG` n'y est pas et ne peut pas y être : Pillow ne
# lit pas le SVG, et un SVG servi depuis notre origine exécuterait son script dans la
# session de celui qui l'affiche.
FORMATS_ACCEPTES = {"PNG", "JPEG", "WEBP", "GIF"}

_MIME = "image/webp"


class AvatarRefuse(Exception):
    """Le fichier n'a pas sa place ici, et le message dit pourquoi."""


@dataclass(frozen=True)
class AvatarPret:
    octets: bytes
    mime: str


def preparer(brut: bytes) -> AvatarPret:
    """Valide, ré-encode et borne. Lève `AvatarRefuse` avec une raison lisible."""
    if not brut:
        raise AvatarRefuse("fichier vide")
    if len(brut) > OCTETS_MAX_EN_ENTREE:
        raise AvatarRefuse(
            f"image trop lourde : {len(brut) // 1024} Kio pour un maximum de "
            f"{OCTETS_MAX_EN_ENTREE // 1024} Kio"
        )

    try:
        # `verify()` lit la structure sans décoder les pixels ; elle rend l'objet
        # inutilisable ensuite, d'où la seconde ouverture. C'est le prix d'un contrôle
        # qui ne demande pas d'allouer l'image entière.
        Image.open(io.BytesIO(brut)).verify()
        ouverte = Image.open(io.BytesIO(brut))
    except DecompressionBombError as exc:
        # Pillow a sa propre garde, et elle se déclenche avant la nôtre sur les cas
        # extrêmes. Elle ne descend pas d'`OSError` : sans cette branche, elle remontait
        # jusqu'à la route et devenait un 500 — une erreur de serveur pour un fichier que
        # l'utilisateur a mal choisi. Trouvé par le test, pas par la relecture.
        raise AvatarRefuse("image aux dimensions déraisonnables") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise AvatarRefuse("fichier illisible comme image") from exc

    if ouverte.format not in FORMATS_ACCEPTES:
        raise AvatarRefuse(
            f"format {ouverte.format or 'inconnu'} non accepté — PNG, JPEG, WebP ou GIF"
        )

    largeur, hauteur = ouverte.size
    if largeur * hauteur > PIXELS_MAX:
        raise AvatarRefuse("image aux dimensions déraisonnables")

    # `convert` avant `thumbnail` : une palette indexée ou un CMJN redimensionnés donnent
    # des couleurs fausses. RGBA garde la transparence, que WebP sait rendre.
    image = ouverte.convert("RGBA")
    image.thumbnail((COTE_MAX, COTE_MAX), Image.Resampling.LANCZOS)

    sortie = io.BytesIO()
    # `save` sur une image neuve, sans `exif=` ni `icc_profile=` : les métadonnées de
    # l'original ne sont pas recopiées. C'est ici que les coordonnées GPS disparaissent.
    image.save(sortie, format="WEBP", quality=82, method=4)
    octets = sortie.getvalue()

    if len(octets) > OCTETS_MAX_EN_SORTIE:
        # Ne devrait pas arriver à 512 pixels de côté, mais une image pathologique
        # pourrait mal se compresser. Mieux vaut refuser que garder l'inattendu.
        raise AvatarRefuse("image impossible à réduire suffisamment")

    return AvatarPret(octets=octets, mime=_MIME)
