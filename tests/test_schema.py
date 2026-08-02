import sqlite3

import pytest

from kg.schema import CURRENT_VERSION, migrate


def test_fresh_migration_and_idempotency() -> None:
    c = sqlite3.connect(":memory:")
    migrate(c)
    first = c.execute("select value from meta where key='schema_version'").fetchone()[0]
    migrate(c)
    assert int(first) == CURRENT_VERSION
    assert c.execute("select name from sqlite_master where type='table' and name='notes'").fetchone()


def test_newer_database_refused() -> None:
    c = sqlite3.connect(":memory:")
    c.execute("create table meta(key text primary key,value text)")
    c.execute("insert into meta values('schema_version','999')")
    c.commit()
    with pytest.raises(RuntimeError, match="db_schema_newer"):
        migrate(c)
