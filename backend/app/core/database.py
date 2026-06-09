from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


def _create_engine() -> Engine:
    connect_args: dict = {}
    engine_kwargs: dict = {"connect_args": connect_args}

    if settings.is_mysql:
        connect_args["charset"] = "utf8mb4"
    elif settings.is_sqlite:
        connect_args["check_same_thread"] = False
    else:
        engine_kwargs["pool_pre_ping"] = True

    engine = create_engine(settings.database_url, **engine_kwargs)

    if settings.is_mysql:

        @event.listens_for(engine, "connect")
        def set_mysql_utf8mb4(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("SET NAMES utf8mb4")
            cursor.close()

    return engine


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
