import sqlite3

from kg import hashbow


def test_extract_is_deterministic_and_sparse() -> None:
    a = hashbow.extract("Postgres is a relational database")
    b = hashbow.extract("Postgres is a relational database")
    assert a == b
    assert all(isinstance(k, int) and 0 <= k < hashbow.DIM for k in a)
    assert any(a.values())


def test_identical_text_closer_than_unrelated() -> None:
    v = hashbow.extract("Postgres primary store")
    same = hashbow.extract("Postgres primary store")
    other = hashbow.extract("completely unrelated gardening words")
    assert hashbow.cosine(v, same) > hashbow.cosine(v, other)
    assert abs(hashbow.cosine(v, v) - 1.0) < 1e-9


def test_l2_norm_matches_manual() -> None:
    vec = {1: 3.0, 2: 4.0}
    assert hashbow.l2(vec) == 5.0


def test_extract_bucket_range_and_sparsity() -> None:
    vec = hashbow.extract("Postgres is a relational database")
    assert len(vec) < 16384
    assert all(0 <= k < 16384 for k in vec)
    assert all(v != 0 for v in vec.values())


def test_projection_uses_same_buckets(tmp_path) -> None:
    from kg.projection import index_all, rebuild
    from kg.schema import migrate
    from kg.storage import Vault

    vault = Vault(tmp_path)
    path = tmp_path / ".brain" / "notes" / "concept"
    path.mkdir(parents=True)
    (tmp_path / ".brain" / ".kg").mkdir(parents=True)
    (path / "nt_aaaaaaaaaaaaaaaa.md").write_text(
        "---\nid: nt_aaaaaaaaaaaaaaaa\nkind: concept\ntitle: Postgres primary store\nstatus: verified\nsource_sha256: "
        + "a" * 64
        + "\ncreated: 2026-01-01\nupdated: 2026-01-01\nrefs: []\ntags: []\nprovenance: []\n---\nBody\n",
        encoding="utf-8",
    )
    conn = sqlite3.connect(tmp_path / ".brain" / ".kg" / "brain.sqlite")
    migrate(conn)
    index_all(vault, conn)
    rows = conn.execute("select feature, weight from vec_features where note_id='nt_aaaaaaaaaaaaaaaa'").fetchall()
    conn.close()
    assert rows
    expected = hashbow.extract("Postgres primary store" + " " + "Body")
    assert dict(rows) == expected
    assert rebuild(vault)["notes"] == 1
