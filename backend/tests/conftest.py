from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import get_db
from app.main import app


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    engine = create_engine(
        get_settings().test_database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
    yield engine
    engine.dispose()


def _override_db(engine: Engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    return _get_db


@pytest.fixture
def client(test_engine: Engine) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = _override_db(test_engine)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_db_down() -> Iterator[TestClient]:
    """Client mà get_db trỏ tới một Postgres không tồn tại."""
    engine = create_engine(
        "postgresql+psycopg://nobody:nobody@127.0.0.1:1/none",
        connect_args={"connect_timeout": 1},
    )
    app.dependency_overrides[get_db] = _override_db(engine)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()
