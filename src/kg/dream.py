from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from collections import defaultdict
from typing import Final

from .ids import diff_id, normalize_title
from .models import DreamOp, ProposedDiff

PASSES: Final[tuple[str, ...]] = (
    "dedup",
    "contradiction",
    "supersede",
    "stale",
    "orphan",
    "open-q",
    "community",
)
_STALE_DAYS: Final[int] = 180
_CONTRADICTION_CAP: Final[int] = 200
_OPERATION_CAP: Final[int] = 500


def _rows(conn: sqlite3.Connection) -> list[tuple[object, ...]]:
    return conn.execute(
        "SELECT id,title,kind,body,status,updated,tags_json,supersedes,source_sha256 "
        "FROM notes WHERE status NOT IN ('tombstone','superseded') ORDER BY id"
    ).fetchall()


def run(
    conn: sqlite3.Connection,
    vault: object | None,
    passes: tuple[str, ...] = PASSES,
) -> ProposedDiff:
    requested = tuple(passes)
    unknown = set(requested) - set(PASSES)
    if unknown:
        raise ValueError("unknown dream pass")
    notes = _rows(conn)
    operations: list[DreamOp] = []
    handlers = {
        "dedup": _dedup,
        "contradiction": _contradiction,
        "supersede": _supersede,
        "stale": _stale,
        "orphan": _orphan,
        "open-q": _open_question,
        "community": _community,
    }
    for pass_name in requested:
        operations.extend(handlers[pass_name](conn, notes))
    normalized = [
        {
            "op": operation.op,
            "id": operation.id,
            "reason": operation.reason,
            "evidence": sorted(operation.evidence),
            "pass_name": operation.pass_name,
        }
        for operation in operations
    ]
    normalized.sort(key=lambda item: (item["pass_name"], item["id"], item["op"], item["evidence"]))
    normalized = normalized[:_OPERATION_CAP]
    return ProposedDiff(
        id=diff_id(normalized),
        status="proposed",
        operations=[DreamOp.model_validate(item) for item in normalized],
    )


def _op(op: str, nid: str, reason: str, evidence: list[str], pass_name: str) -> DreamOp:
    return DreamOp(op=op, id=nid, reason=reason, evidence=sorted(set(evidence)), pass_name=pass_name)  # type: ignore[arg-type]


def _dedup(conn: sqlite3.Connection, notes: list[tuple[object, ...]]) -> list[DreamOp]:
    groups: dict[str, list[str]] = defaultdict(list)
    for row in notes:
        groups[normalize_title(str(row[1]))].append(str(row[0]))
    operations: list[DreamOp] = []
    for ids in groups.values():
        if len(ids) < 2:
            continue
        keeper, *duplicates = sorted(ids)
        operations.extend(_op("supersede", duplicate, "duplicate normalized title", [keeper], "dedup") for duplicate in duplicates)
    return operations


def _contradiction(conn: sqlite3.Connection, notes: list[tuple[object, ...]]) -> list[DreamOp]:
    buckets: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    for row in notes:
        tags = json.loads(str(row[6]) or "[]")
        key = str(row[8]) + "|" + ",".join(sorted(str(tag) for tag in tags))
        if len(buckets[key]) < _CONTRADICTION_CAP:
            buckets[key].append(row)
    operations: list[DreamOp] = []
    for group in buckets.values():
        # Two "not X" notes both contradict the same "X" note; group by the
        # negation-stripped form so the shared claim is dropped once, not per
        # negation. The pair check still uses the strict substring rule.
        by_form: dict[str, list[tuple[object, ...]]] = defaultdict(list)
        for row in group:
            by_form[str(row[3]).casefold().replace("not ", "")].append(row)
        for members in by_form.values():
            drops: dict[str, list[str]] = {}
            for left_index, left in enumerate(members):
                left_body = str(left[3]).casefold()
                for right in members[left_index + 1 :]:
                    if not _contradictory(left_body, str(right[3]).casefold()):
                        continue
                    loser = max(str(left[0]), str(right[0]))
                    winner = min(str(left[0]), str(right[0]))
                    drops.setdefault(loser, []).append(winner)
            for loser, winners in sorted(drops.items()):
                operations.append(_op("drop", loser, "possible contradiction", winners, "contradiction"))
    return operations


def _contradictory(left: str, right: str) -> bool:
    if "not " in left:
        positive = left.replace("not ", "")
        return positive in right
    if "not " in right:
        positive = right.replace("not ", "")
        return positive in left
    return False


def _supersede(conn: sqlite3.Connection, notes: list[tuple[object, ...]]) -> list[DreamOp]:
    live = {str(row[0]) for row in notes}
    operations: list[DreamOp] = []
    for row in notes:
        target = row[7]
        if target and str(target) in live:
            operations.append(_op("supersede", str(target), "superseded by newer note", [str(row[0])], "supersede"))
    return operations


def _stale(conn: sqlite3.Connection, notes: list[tuple[object, ...]]) -> list[DreamOp]:
    cutoff = _dt.datetime.now(_dt.UTC) - _dt.timedelta(days=_STALE_DAYS)
    operations: list[DreamOp] = []
    for row in notes:
        try:
            updated = _dt.datetime.fromisoformat(str(row[5]))
        except ValueError:
            continue
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=_dt.UTC)
        outgoing = conn.execute("SELECT 1 FROM edges WHERE src=? LIMIT 1", (row[0],)).fetchone()
        if updated < cutoff and outgoing is None:
            operations.append(_op("drop", str(row[0]), "stale with no outgoing edge", [], "stale"))
    return operations


def _orphan(conn: sqlite3.Connection, notes: list[tuple[object, ...]]) -> list[DreamOp]:
    operations: list[DreamOp] = []
    for row in notes:
        connected = conn.execute(
            "SELECT 1 FROM edges WHERE src=? OR dst=? LIMIT 1", (row[0], row[0])
        ).fetchone()
        if connected is None:
            operations.append(_op("drop", str(row[0]), "orphan with no edges", [], "orphan"))
    return operations


def _open_question(conn: sqlite3.Connection, notes: list[tuple[object, ...]]) -> list[DreamOp]:
    operations: list[DreamOp] = []
    for row in notes:
        if str(row[1]).rstrip().endswith("?") or str(row[3]).rstrip().endswith("?"):
            operations.append(_op("drop", str(row[0]), "open question signal", [], "open-q"))
    return operations


def _community(conn: sqlite3.Connection, notes: list[tuple[object, ...]]) -> list[DreamOp]:
    parent = {str(row[0]): str(row[0]) for row in notes}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for src, dst in conn.execute("SELECT src,dst FROM edges WHERE confidence > 0.8 ORDER BY src,dst"):
        if str(src) in parent and str(dst) in parent:
            parent[find(str(src))] = find(str(dst))
    groups: dict[str, list[str]] = defaultdict(list)
    for node in sorted(parent):
        groups[find(node)].append(node)
    operations: list[DreamOp] = []
    for root, members in sorted(groups.items()):
        if len(members) > 1:
            for member in members:
                if member != root:
                    operations.append(_op("drop", member, "dense confidence community", [root], "community"))
    return operations
