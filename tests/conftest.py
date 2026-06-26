"""Shared test configuration.

Provide dummy environment values so ``ghostcal.config.Settings`` can be instantiated in tests
without a real .env. These are non-secret placeholders, never used against real infrastructure.
"""

from __future__ import annotations

import os

os.environ.setdefault("GHOSTCAL_DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("GHOSTCAL_REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("GHOSTCAL_SECRET_KEY", "test-secret-key-at-least-32-characters-long")
os.environ.setdefault("GHOSTCAL_TOKEN_ENCRYPTION_KEY", "test-encryption-key-at-least-32-chars-long")
