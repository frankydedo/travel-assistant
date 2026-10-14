"""Test infrastructure: PostgreSQL, like the application (ADR-0014).

A throwaway Postgres container is started with testcontainers (or ``TEST_DATABASE_URL`` is used, e.g. a
CI service). The schema is created by running the real Alembic migrations, the catalog is seeded once
into a template database, and every test gets its own clone (``CREATE DATABASE ... TEMPLATE``), because
bookings mutate inventory.
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

# No network and no model download: keyword retrieval and the mock provider only.
os.environ["RETRIEVER"] = "keyword"
os.environ["LLM_CHAIN"] = "mock"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import URL, make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import db  # noqa: E402
from app.api.deps import get_rate_limiter  # noqa: E402
from app.auth import get_current_user, provision_user  # noqa: E402
from app.main import app  # noqa: E402
from app.seed.generate import generate  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent
TEMPLATE_DB = "travel_template"


@pytest.fixture(scope="session")
def server_url() -> Iterator[URL]:
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield make_url(url)
        return
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as postgres:
        yield make_url(postgres.get_connection_url())


def _admin(server_url: URL):
    return create_engine(server_url.set(database="postgres"), isolation_level="AUTOCOMMIT")


@pytest.fixture(scope="session")
def template(server_url) -> str:
    admin = _admin(server_url)
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEMPLATE_DB}"))
        conn.execute(text(f"CREATE DATABASE {TEMPLATE_DB}"))
    admin.dispose()

    url = server_url.set(database=TEMPLATE_DB)
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    command.upgrade(config, "head")  # the real migrations, not create_all

    engine = create_engine(url)
    with Session(engine) as session:
        generate(session)
    engine.dispose()  # a template database must have no open connections
    return TEMPLATE_DB


@pytest.fixture
def engine(server_url, template):
    name = f"test_{uuid.uuid4().hex[:12]}"
    admin = _admin(server_url)
    with admin.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name} TEMPLATE {template}"))
    engine = create_engine(server_url.set(database=name))
    db.configure_engine(engine)
    yield engine
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {name}"))
    admin.dispose()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    with db.session_factory()() as s:
        yield s


class Users:
    """Switch the authenticated user without real JWTs."""

    def __init__(self):
        self.current = "alice"

    def dependency(self):
        def _user():
            with db.session_factory()() as s:
                user = provision_user(s, {"sub": self.current, "preferred_username": self.current})
                s.expunge(user)
                return user

        return _user


@pytest.fixture
def users(engine) -> Iterator[Users]:
    users = Users()
    app.dependency_overrides[get_current_user] = users.dependency()
    get_rate_limiter.cache_clear()
    yield users
    app.dependency_overrides.clear()


@pytest.fixture
def client(users) -> TestClient:
    return TestClient(app)
