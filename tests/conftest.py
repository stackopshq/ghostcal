"""Shared test configuration.

Goal: unit tests must run without any infrastructure (CI), while integration tests use the real
database from ``.env`` when it exists (local dev).

- Always provide non-secret placeholders for fields unit tests may touch.
- Only inject placeholder database URLs when there is NO ``.env`` (i.e. CI): that lets
  ``create_app()`` import, while the integration fixtures fail to connect and skip. When a
  ``.env`` exists, its real URLs are used and the integration tests actually run.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("GHOSTCAL_SECRET_KEY", "test-secret-key-at-least-32-characters-long")
os.environ.setdefault("GHOSTCAL_TOKEN_ENCRYPTION_KEY", "test-encryption-key-at-least-32-chars-long")
os.environ.setdefault("GHOSTCAL_REDIS_URL", "redis://localhost:6379/0")

if not Path(".env").exists():
    _placeholder = "postgresql+asyncpg://test:test@localhost:5432/ghostcal_absent"
    os.environ.setdefault("GHOSTCAL_DATABASE_URL", _placeholder)
    os.environ.setdefault("GHOSTCAL_DATABASE_ADMIN_URL", _placeholder)
