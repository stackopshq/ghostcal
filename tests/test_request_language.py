"""Which language an `Accept-Language` header asks for, among the two the server names things in."""

from __future__ import annotations

import pytest

from ghostcal.presentation.language import preferred_language


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, "fr"),
        ("", "fr"),
        ("garbage;;;q=x", "fr"),
        ("*", "fr"),
        ("it", "fr"),
        ("fr", "fr"),
        ("en", "en"),
        ("EN-us", "en"),
        # Weighted: French first. Werkzeug's own best_match answers "en" here.
        ("fr-CH;q=0.9, en;q=0.8", "fr"),
        ("en-GB,en;q=0.9,fr;q=0.8", "en"),
        ("de-DE,de;q=0.9,en;q=0.5", "en"),
        # Order in the header is not order of preference: weights are.
        ("en;q=0.2, fr;q=0.9", "fr"),
        # q=0 means "not acceptable", not "least preferred".
        ("en;q=0, fr;q=0.1", "fr"),
        ("en;q=0", "fr"),
    ],
)
def test_preferred_language(header: str | None, expected: str) -> None:
    assert preferred_language(header) == expected
