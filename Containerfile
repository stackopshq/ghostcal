# GhostCal backend image. Build: podman build -t ghostcal:dev .
# Multi-stage: deps resolved with uv against the locked manifest, runtime kept minimal.
#
# Rocky Linux, like the hosts it runs on, not Debian. Rocky 10 ships Python 3.12, so the
# interpreter is a pinned CPython installed by uv, at the same path in both stages: the venv's
# python is a link to it.
#
# Every input is pinned: the Rocky base by tag and multi-arch index digest, uv by digest, Python
# by exact version. A tag is mutable, so an unpinned build is not reproducible and a scan of it
# says nothing about what ships tomorrow. Update deliberately — after pulling the new tag,
#   podman image inspect <tag> --format '{{index .RepoDigests 0}}'
# (for the Rocky base, take the index digest, so arm64 builds stay possible).

ARG ROCKY_IMAGE=docker.io/rockylinux/rockylinux:10.2.20260525.0-minimal@sha256:bc5c1e7a2ec7f4bcef1e51c7f0ebb2d43f05409e0108cdd34f693921d0604360
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff
ARG PYTHON_VERSION=3.14.9

FROM ${UV_IMAGE} AS uv

FROM ${ROCKY_IMAGE} AS builder
ARG PYTHON_VERSION

COPY --from=uv /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_PYTHON=${PYTHON_VERSION}

# The standalone CPython bundles pip, and pip vendors its own urllib3, msgpack and setuptools:
# Trivy flags them (HIGH, fixed upstream) though nothing here runs pip — uv builds the venv, which
# has none. So the interpreter ships without pip or ensurepip's wheels.
RUN uv python install "${PYTHON_VERSION}" \
 && rm -rf /opt/python/cpython-*/lib/python3.*/site-packages/pip \
           /opt/python/cpython-*/lib/python3.*/site-packages/pip-*.dist-info \
           /opt/python/cpython-*/lib/python3.*/ensurepip/_bundled \
           /opt/python/cpython-*/bin/pip*
ENV UV_PYTHON_DOWNLOADS=never

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


FROM ${ROCKY_IMAGE} AS runtime

# ─── The distribution's security fixes ───
#
# The base is pinned by digest, which also freezes the OS packages it carries. They age while the
# digest does not: on 2026-09-25 Trivy found three HIGH CVEs in pcre2 that no dependency lockfile
# shows, in the largest surface of the shipped artefact. So every build upgrades the OS packages
# (CI builds with --no-cache for this to run). Trivy fails on any HIGH/CRITICAL fixed upstream,
# so upgrading only the offending package would turn the next errata red. The digest stays pinned:
# it is the package layer that floats, not the image.
#
# tzdata: zoneinfo is how every event time is resolved; shadow-utils (useradd) is already in the
# minimal image.
RUN microdnf -y upgrade \
 && microdnf -y install --setopt=install_weak_deps=0 tzdata \
 && microdnf clean all

# Non-root runtime user.
RUN groupadd --system app && useradd --system --gid app --home /app app

COPY --from=builder /opt/python /opt/python
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
