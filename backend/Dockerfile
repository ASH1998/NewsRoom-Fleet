# Newsroom Fleet backend — Cloud Run image.
#
# The cloud extra is installed here, but which implementation actually runs is
# still decided by environment variables at start-up. The same image serves the
# deterministic fixture demo and a live ADK review.
FROM python:3.13-slim

# uv is the project's package manager (no global pip installs, per AGENTS.md).
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Dependency layer first so source edits do not re-resolve the environment.
COPY pyproject.toml uv.lock* ./
RUN uv sync --extra cloud --no-install-project --no-dev

COPY src ./src
RUN uv sync --extra cloud --no-dev

# Cloud Run supplies PORT. One worker keeps the in-process fallback path
# single-writer; horizontal scaling is Cloud Run's job, not uvicorn's.
ENV PORT=8080
EXPOSE 8080
CMD exec uv run uvicorn newsroom_fleet.api.app:app --host 0.0.0.0 --port ${PORT} --workers 1
