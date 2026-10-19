"""Database setup supporting SQLite by default and PostgreSQL / Supabase via DATABASE_URL."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DATABASE_URL, DB_SCHEMA, IS_PRODUCTION

# Setup Base with isolated PostgreSQL schema
Base = declarative_base()
Base.metadata.schema = DB_SCHEMA

def normalize_db_url(url: str) -> str:
    """Normalizes postgres:// and postgresql:// to postgresql+psycopg2:// for reliable driver dialect."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


is_sqlite = DATABASE_URL.startswith("sqlite")

if is_sqlite:
    # For SQLite, translate isolated PostgreSQL schema to default SQLite namespace
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    ).execution_options(schema_translate_map={DB_SCHEMA: None})
else:
    # For PostgreSQL / Supabase: connection pooling, keepalive, and pre-ping
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )
    # When in production, verify connectivity immediately on boot
    if IS_PRODUCTION:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1;"))
        except Exception as e:
            raise RuntimeError(
                f"FATAL DATABASE ERROR: Could not establish connection to production PostgreSQL database: {e}"
            ) from e

    # Ensure dedicated schema exists before table creation (non-fatal if permissions already restricted)
    try:
        with engine.connect() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA}"))
            conn.commit()
    except Exception as e:
        print(f"[Database] Schema '{DB_SCHEMA}' initialization notice: {e}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

