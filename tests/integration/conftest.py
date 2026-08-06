"""통합 테스트 공용 fixture.

실제 PostgreSQL 연결이 필요하다. 설정·환경변수가 없으면 skip 한다.
`pytest -m "not integration"` 으로 제외할 수 있다.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from lifelaw_web.settings import Settings, SettingsError, load_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    try:
        return load_settings()
    except SettingsError as exc:
        pytest.skip(f"설정·환경변수 없음: {exc}")


@pytest.fixture
def conn(settings: Settings) -> Iterator[Any]:
    import psycopg

    from lifelaw_web.db.connection import connect

    try:
        with connect(settings) as connection:
            yield connection
    except psycopg.OperationalError as exc:  # pragma: no cover - 환경 의존
        pytest.skip(f"DB 연결 불가: {type(exc).__name__}")


@pytest.fixture(scope="session")
def runtime_role(settings: Settings) -> str:
    return settings.secrets.db_user
