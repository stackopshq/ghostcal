# GhostCal backend image. Build: podman build -t ghostcal:dev .
# Multi-stage: deps resolved with uv against the locked manifest, runtime kept minimal.
#
# Base images are pinned by digest, with the tag kept alongside for readability. A tag is mutable:
# `python:3.14-slim-bookworm` is a different image this month than last, so an unpinned build is
# not reproducible and a scan of it says nothing about what ships tomorrow. Update deliberately —
# `podman image inspect <tag> --format '{{index .RepoDigests 0}}'` after pulling the new tag.

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Install dependencies first (cache-friendly: changes to source don't re-resolve deps).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Install the project itself.
COPY src ./src
COPY README.md LICENSE NOTICE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM docker.io/library/python:3.14-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30 AS runtime

# ─── Les correctifs de sécurité de la distribution ───
#
# L'image de base est épinglée par condensat, ce qui fige **aussi** l'état des paquets
# Debian qu'elle embarque. Ils vieillissent pendant que le condensat, lui, ne bouge pas.
#
# Constaté le 2026-09-25 : Trivy a trouvé trois CVE HIGH dans `libpcre2-8-0` — écriture
# hors limites, corruption mémoire (CVE-2026-86145, -89157, -89161) — présentes en
# `10.42-1` et corrigées en `10.42-1+deb12u1`. Elles n'apparaissent dans aucun verrou de
# dépendances : `osv-scanner` était vert. C'est le système sous les dépendances, et c'est
# la plus grande surface de l'artefact déployé.
#
# `upgrade` plutôt que le seul paquet fautif : Trivy échoue sur tout HIGH/CRITICAL
# **corrigé en amont**, donc n'en traiter qu'un rendrait la construction rouge à la
# prochaine publication de Debian. Une construction qu'on ne peut pas rendre verte apprend
# à ignorer le contrôle.
#
# Le condensat reste épinglé : c'est la couche de paquets qui flotte, pas l'image. On
# échange une reproductibilité au paquet près contre des correctifs de sécurité appliqués
# sans intervention — dans une image livrée, c'est le bon sens de l'échange.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user.
RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src
# Migrations + Alembic config so the image can run `alembic upgrade head`.
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app alembic.ini ./alembic.ini

# Where celery beat keeps its schedule file, mounted as a volume in compose. Created here, owned
# by the runtime user: a named volume inherits the ownership of its mount point from the image, so
# without this the non-root beat process cannot write to a fresh volume and exits at startup.
RUN mkdir -p /var/lib/ghostcal && chown app:app /var/lib/ghostcal

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app
EXPOSE 8000

# Override with the celery worker command for the worker deployment.
CMD ["uvicorn", "ghostcal.presentation.api:app", "--host", "0.0.0.0", "--port", "8000"]
