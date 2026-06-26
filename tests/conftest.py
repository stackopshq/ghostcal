"""Shared test configuration.

Provide non-secret placeholder values for config fields that unit tests may touch, without
shadowing the real database URLs: integration tests need the actual ``GHOSTCAL_DATABASE_URL`` /
``GHOSTCAL_DATABASE_ADMIN_URL`` from ``.env`` (or the CI environment), so those are deliberately
NOT set here.
"""

from __future__ import annotations

import os

os.environ.setdefault("GHOSTCAL_SECRET_KEY", "test-secret-key-at-least-32-characters-long")
os.environ.setdefault("GHOSTCAL_TOKEN_ENCRYPTION_KEY", "test-encryption-key-at-least-32-chars-long")
os.environ.setdefault("GHOSTCAL_REDIS_URL", "redis://localhost:6379/0")
