from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    src = os.getenv("SQLITE_PATH", "/data/sql_app.db")
    src_path = Path(src)
    if not src_path.exists():
        raise SystemExit(f"sqlite not found: {src_path}")

    con = sqlite3.connect(str(src_path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT id, username, password, project, other_data FROM user_data")
    rows = cur.fetchall()
    con.close()

    inserted = 0
    skipped = 0
    with engine().begin() as conn:
        for r in rows:
            username = r["username"]
            password = r["password"]
            project = r["project"]
            other_raw = r["other_data"]
            other = None
            if other_raw is not None:
                try:
                    other = json.loads(other_raw) if isinstance(other_raw, str) else other_raw
                except Exception:
                    other = {}
            # upsert by username
            res = conn.execute(
                text(
                    """
                    INSERT INTO users(username, password, project, other_data)
                    VALUES (:u, :p, :proj, :od)
                    ON CONFLICT (username) DO NOTHING
                    """
                ),
                {"u": username, "p": password, "proj": project, "od": other},
            )
            if res.rowcount and res.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

    print(f"done: inserted={inserted} skipped={skipped} total={len(rows)}")


if __name__ == "__main__":
    main()

