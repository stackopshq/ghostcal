"""The language a request asks for, read from its standard `Accept-Language` header.

Only what the server itself names needs it (the default calendar). The language is never stored:
it travels with the request that needs it (see the 2026-10-15 decision in
`application/bilingual.py`).
"""

from __future__ import annotations

from typing import Annotated, get_args

from fastapi import Header
from werkzeug.datastructures import LanguageAccept
from werkzeug.http import parse_accept_header

from ghostcal.application.calendar import Language

_KNOWN: tuple[Language, ...] = get_args(Language)
_FALLBACK: Language = "fr"


def preferred_language(header: str | None) -> Language:
    """The first acceptable tag, by weight, whose primary subtag the server knows; else French.

    The header is parsed by Werkzeug, not split here: RFC 9110 gives it weights, and
    `fr-CH;q=0.9, en;q=0.8` means French. Werkzeug's own `best_match` is not used either: it tries
    exact matches first, so on that header it answers `en`.
    """
    if not header:
        return _FALLBACK
    for tag, quality in parse_accept_header(header, LanguageAccept):
        if quality <= 0:
            continue
        primary = tag.split("-", 1)[0].split("_", 1)[0].lower()
        if primary in _KNOWN:
            return primary
    return _FALLBACK


def request_language(
    accept_language: Annotated[str | None, Header()] = None,
) -> Language:
    return preferred_language(accept_language)
