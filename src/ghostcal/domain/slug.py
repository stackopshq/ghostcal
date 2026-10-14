"""URL slugs for public pages (booking types, polls)."""

from __future__ import annotations

import secrets
import unicodedata


def slugify(title: str, *, max_length: int, fallback: str) -> str:
    """An ASCII slug with a random suffix, e.g. ``"Découverte 15'"`` -> ``decouverte-15-3fa2c1``.

    Accented letters are transliterated (é -> e, ß -> ss) rather than kept: a kept "é"
    made links like ``/clara/d%C3%A9couverte-…`` that read as broken once copied.
    The random suffix guarantees uniqueness without surfacing slug conflicts.
    """
    ascii_title = (
        unicodedata.normalize("NFKD", title.replace("ß", "ss"))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    base = "".join(c if c.isalnum() else "-" for c in ascii_title)
    base = "-".join(filter(None, base.split("-")))[:max_length].strip("-") or fallback
    return f"{base}-{secrets.token_hex(3)}"
