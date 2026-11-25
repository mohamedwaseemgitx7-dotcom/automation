"""One-time copy of the laptop SQLite database into Postgres (config, contacts, knowledge + embeddings, chats, logs).

Usage (target must be empty; tables are created if missing):
    python scripts/copy_sqlite_to_postgres.py --src storage/agent.db --dst "postgresql+psycopg://agent:***@host:5432/agent"
The source file is only read, never changed."""
import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.db import Base  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    a = ap.parse_args()
    src = create_engine(f"sqlite:///{Path(a.src).resolve().as_posix()}?mode=ro")
    dst = create_engine(a.dst)
    Base.metadata.create_all(dst)
    with src.connect() as s, dst.begin() as d:
        for t in Base.metadata.sorted_tables:            # parents before children (foreign keys)
            if d.scalar(select(func.count()).select_from(t)):
                sys.exit(f"target table {t.name} is not empty - stopping, nothing overwritten")
        for t in Base.metadata.sorted_tables:
            rows = [dict(r._mapping) for r in s.execute(select(t))]
            if rows:
                d.execute(t.insert(), rows)
            if dst.dialect.name == "postgresql" and "id" in t.c:
                d.execute(text(f"SELECT setval(pg_get_serial_sequence('{t.name}', 'id'), "
                               f"COALESCE((SELECT MAX(id) FROM {t.name}), 0) + 1, false)"))
            print(f"{t.name}: {len(rows)} rows")
    print("done")


if __name__ == "__main__":
    main()
