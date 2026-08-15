"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from newsroom_fleet.api.routes import router
from newsroom_fleet.bootstrap import build_fleet
from newsroom_fleet.config import Settings
from newsroom_fleet.observability.tracing import instrument_app


def create_app(settings: Settings | None = None) -> FastAPI:
    fleet = build_fleet(settings)
    app = FastAPI(
        title="Newsroom Fleet",
        version="0.1.0",
        description="Institutional multi-agent verification for local newsrooms",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=fleet.settings.allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = fleet.settings
    app.state.repo = fleet.repo
    app.state.service = fleet.service
    # What was actually constructed, not what was requested — a cloud component
    # that fell back to its local implementation must say so.
    app.state.resolved = fleet.resolved
    app.include_router(router)
    instrument_app(app)
    return app


app = create_app()
