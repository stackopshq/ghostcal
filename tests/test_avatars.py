"""Ce qu'on accepte comme avatar, et ce qu'on en fait.

Ces tests ne touchent ni base ni réseau : `preparer` est de la logique pure, et c'est la
raison pour laquelle elle est un module à part plutôt qu'un bout de route.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from ghostcal.application.avatars import (
    COTE_MAX,
    OCTETS_MAX_EN_ENTREE,
    OCTETS_MAX_EN_SORTIE,
    AvatarRefuse,
    preparer,
)


def _image(largeur: int, hauteur: int, format_: str = "PNG", **enregistrer: object) -> bytes:
    tampon = io.BytesIO()
    Image.new("RGB", (largeur, hauteur), (12, 34, 56)).save(tampon, format=format_, **enregistrer)
    return tampon.getvalue()


def test_une_image_valide_ressort_en_webp_bornee() -> None:
    pret = preparer(_image(1024, 768))
    assert pret.mime == "image/webp"
    image = Image.open(io.BytesIO(pret.octets))
    assert image.format == "WEBP"
    assert max(image.size) <= COTE_MAX
    assert len(pret.octets) <= OCTETS_MAX_EN_SORTIE


def test_les_proportions_sont_gardees() -> None:
    """Un avatar déformé se remarque ; `thumbnail` préserve le rapport, on le vérifie."""
    image = Image.open(io.BytesIO(preparer(_image(1000, 500)).octets))
    assert image.size == (COTE_MAX, COTE_MAX // 2)


def test_une_petite_image_n_est_pas_agrandie() -> None:
    image = Image.open(io.BytesIO(preparer(_image(64, 64)).octets))
    assert image.size == (64, 64)


def test_les_metadonnees_exif_disparaissent() -> None:
    """Le point de cette fonction : une photo de téléphone porte souvent son GPS."""
    exif = Image.Exif()
    exif[0x010E] = "description qui ne doit pas survivre"
    avec_exif = _image(200, 200, "JPEG", exif=exif)
    assert b"description qui ne doit pas survivre" in avec_exif  # le témoin est valide

    pret = preparer(avec_exif)
    assert b"description qui ne doit pas survivre" not in pret.octets
    assert not Image.open(io.BytesIO(pret.octets)).getexif()


@pytest.mark.parametrize("format_", ["PNG", "JPEG", "WEBP", "GIF"])
def test_les_quatre_formats_acceptes_passent(format_: str) -> None:
    assert preparer(_image(300, 300, format_)).mime == "image/webp"


def test_un_fichier_vide_est_refuse() -> None:
    with pytest.raises(AvatarRefuse, match="vide"):
        preparer(b"")


def test_un_fichier_trop_lourd_est_refuse_sans_etre_decode() -> None:
    with pytest.raises(AvatarRefuse, match="trop lourde"):
        preparer(b"\x00" * (OCTETS_MAX_EN_ENTREE + 1))


def test_ce_qui_n_est_pas_une_image_est_refuse() -> None:
    with pytest.raises(AvatarRefuse, match="illisible"):
        preparer(b"ceci est du texte, pas une image")


def test_le_svg_est_refuse() -> None:
    """Un SVG est un document XML qui peut porter du script ; servi depuis notre origine,
    il s'exécuterait dans la session de celui qui l'affiche."""
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    with pytest.raises(AvatarRefuse):
        preparer(svg)


def test_une_bombe_de_decompression_est_refusee() -> None:
    """Quelques kilo-octets compressés, des gigaoctets une fois décodés. La borne
    d'entrée ne l'arrête pas — c'est la borne de dimensions qui le fait."""
    tampon = io.BytesIO()
    Image.new("L", (20000, 20000)).save(tampon, format="PNG")
    bombe = tampon.getvalue()
    assert len(bombe) < OCTETS_MAX_EN_ENTREE  # elle passe bien la première borne

    with pytest.raises(AvatarRefuse, match="déraisonnables"):
        preparer(bombe)


def test_un_entete_png_suivi_de_n_importe_quoi_est_refuse() -> None:
    """On ne valide pas sur un préfixe d'octets : Pillow doit vraiment décoder."""
    with pytest.raises(AvatarRefuse, match="illisible"):
        preparer(b"\x89PNG\r\n\x1a\n" + b"pas du tout un PNG")
