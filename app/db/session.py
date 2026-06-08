from sqlmodel import SQLModel, Session, create_engine

from app.core.config import get_settings

settings = get_settings()

# SQLite needs check_same_thread=False for FastAPI's threaded request handling.
# PostgreSQL doesn't need this — the condition keeps both configs clean.
_connect_args = (
    {"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    echo=False,  # set True to log SQL statements during development
)


def create_db_and_tables() -> None:
    """Create all tables defined by SQLModel classes. Called once at startup."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency — yields a DB session per request."""
    with Session(engine) as session:
        yield session
