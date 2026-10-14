"""Public-page slugs stay ASCII so copied links read as links."""

from __future__ import annotations

import re

from ghostcal.domain.slug import slugify

SUFFIX = r"-[0-9a-f]{6}$"


def test_accents_are_transliterated() -> None:
    slug = slugify("Découverte de 15 minutes", max_length=80, fallback="event")
    assert re.fullmatch(r"decouverte-de-15-minutes" + SUFFIX, slug)


def test_german_and_ligatures() -> None:
    assert slugify("Straße Œuvre", max_length=80, fallback="event").startswith("strasse-uvre")


def test_only_symbols_falls_back() -> None:
    assert re.fullmatch("poll" + SUFFIX, slugify("✨ 🎉", max_length=60, fallback="poll"))


def test_length_is_bounded_without_trailing_dash() -> None:
    slug = slugify("a" * 79 + " b", max_length=80, fallback="event")
    base = slug.rsplit("-", 1)[0]
    assert len(base) <= 80 and not base.endswith("-")


def test_result_is_url_safe() -> None:
    slug = slugify("Réunion d'équipe : bilan / Q4 ?", max_length=80, fallback="event")
    assert re.fullmatch(r"[a-z0-9-]+", slug)
