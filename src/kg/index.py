from __future__ import annotations

import sqlite3

from .projection import index_all, rebuild as rebuild_projection
from .schema import migrate
from .storage import Vault
from .wiki import generate


def run(vault: Vault, rebuild: bool = False) -> tuple[dict[str, object], int]:
    if rebuild:
        data = rebuild_projection(vault)
        errors = int(data["errors"])
    else:
        db = vault.brain / ".kg" / "brain.sqlite"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db)
        migrate(conn)
        errors = index_all(vault, conn)
        conn.close()
        data = {"notes": 0, "errors": errors}
    data.update(generate(vault))
    return data, 1 if errors else 0
