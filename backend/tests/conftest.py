from __future__ import annotations

import pytest

from newsroom_fleet.config import Settings
from newsroom_fleet.orchestration.pipeline import FleetService
from newsroom_fleet.persistence.sqlite import SQLiteRepository
from newsroom_fleet.security.screening import HeuristicScreener


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(db_path=tmp_path / "test.sqlite3")


@pytest.fixture
def repo(settings) -> SQLiteRepository:
    repository = SQLiteRepository(settings.db_path)
    yield repository
    repository.close()


@pytest.fixture
def service(settings, repo) -> FleetService:
    return FleetService(settings, repo, HeuristicScreener())
