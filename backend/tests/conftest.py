from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai import openai_client
from app.core.config import BACKEND_DIR, get_settings
from app.core.db import get_db
from app.main import app
from tests.fake_embeddings import fake_embed_raw


@pytest.fixture(autouse=True)
def _offline_embeddings(request, monkeypatch):
    """Test thường không gọi OpenAI Embeddings (Phase 15): thay bằng vector giả deterministic.
    Test `@pytest.mark.ai` dùng API thật."""
    if request.node.get_closest_marker("ai") is None:
        monkeypatch.setattr(openai_client, "_embed_raw", fake_embed_raw)


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """Engine tới DB test (`pfa_test`), đã `alembic upgrade head` (có seed categories)."""
    url = get_settings().test_database_url
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    yield engine
    engine.dispose()


@pytest.fixture
def db_connection(test_engine: Engine) -> Iterator[Connection]:
    with test_engine.connect() as connection:
        outer = connection.begin()
        yield connection
        outer.rollback()


@pytest.fixture
def db(db_connection: Connection) -> Iterator[Session]:
    """Session của 1 test: `commit()` trong code chỉ release SAVEPOINT, cuối test rollback hết."""
    session = Session(
        bind=db_connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    yield session
    session.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    def _get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


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
