from __future__ import annotations

import math
import re
import sqlite3
from typing import Final

from . import hashbow

RRF_K: Final[int] = 60
MAX_HOPS: Final[int] = 4
SEED_CAP: Final[int] = 60
VISITED_CAP: Final[int] = 2000
RELATION_WEIGHTS: Final[dict[str, float]] = {
    "causes": 1.0,
    "depends_on": 0.9,
    "supports": 0.6,
    "supersedes": 0.5,
    "contradicts": 0.2,
    "related_to": 0.3,
    "mentions": 0.15,
}
_VALID_DIRECTIONS = {"both", "in", "out"}
_VALID_STRATEGIES = {"adaptive", "lexical"}
_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def _fts_query(query: str) -> str:
    return " ".join(f'"{token}"' for token in _TOKEN.findall(query))


def _like_tokens(query: str) -> list[str]:
    return _TOKEN.findall(query)


def lexical_seed(conn: sqlite3.Connection, query: str, limit: int) -> list[tuple[str, float]]:
    if limit <= 0:
        return []
    cap = min(3 * limit, SEED_CAP)
    fts = _fts_query(query)
    if not fts:
        return []
    try:
        rows = conn.execute(
            "SELECT notes.id, bm25(notes_fts) AS score "
            "FROM notes_fts JOIN notes ON notes.rowid = notes_fts.rowid "
            "WHERE notes_fts MATCH ? AND notes.status NOT IN ('tombstone','superseded') "
            "ORDER BY score ASC, notes.id LIMIT ?",
            (fts, cap),
        ).fetchall()
        # SQLite BM25 is lower-is-better; expose a conventional higher-is-better score.
        return [(str(nid), -float(score)) for nid, score in rows]
    except sqlite3.OperationalError:
        tokens = _like_tokens(query)
        if not tokens:
            return []
        clauses = " OR ".join("title LIKE ? OR body LIKE ?" for _ in tokens)
        params: list[object] = []
        for token in tokens:
            like = f"%{token}%"
            params.extend((like, like))
        rows = conn.execute(
            f"SELECT id FROM notes WHERE status NOT IN ('tombstone','superseded') AND ({clauses}) "
            "ORDER BY id LIMIT ?",
            (*params, cap),
        ).fetchall()
        return [(str(nid), 0.0) for (nid,) in rows]


def vector_seed(conn: sqlite3.Connection, query: str, limit: int) -> list[tuple[str, float]]:
    if limit <= 0:
        return []
    qv = hashbow.extract(query)
    if not qv:
        return []
    cap = min(3 * limit, SEED_CAP)
    placeholders = ",".join("?" for _ in qv)
    rows = conn.execute(
        f"SELECT vf.note_id, vf.feature, vf.weight FROM vec_features vf "
        f"JOIN notes n ON n.id = vf.note_id WHERE vf.feature IN ({placeholders}) "
        "AND n.status NOT IN ('tombstone','superseded')",
        tuple(qv),
    ).fetchall()
    candidate_ids = {str(note_id) for note_id, _, _ in rows}
    if not candidate_ids:
        return []
    vectors: dict[str, dict[int, float]] = {nid: {} for nid in candidate_ids}
    for note_id, feature, weight in rows:
        vectors[str(note_id)][int(feature)] = float(weight)
    norms = dict(
        conn.execute(
            f"SELECT note_id, l2 FROM doc_norms WHERE note_id IN ({','.join('?' for _ in candidate_ids)})",
            tuple(sorted(candidate_ids)),
        ).fetchall()
    )
    ranked = [
        (nid, hashbow.cosine(qv, vector, float(norms.get(nid, 0.0))))
        for nid, vector in vectors.items()
    ]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked[:cap]


def validate_query_params(
    hops: int, direction: str, limit: int, relations: tuple[str, ...] | list[str] = (), strategy: str = "adaptive"
) -> None:
    if not isinstance(hops, int) or isinstance(hops, bool) or not 0 <= hops <= MAX_HOPS:
        raise ValueError(f"hops must be 0..{MAX_HOPS}")
    if direction not in _VALID_DIRECTIONS:
        raise ValueError("unknown direction")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("limit must be positive")
    if strategy not in _VALID_STRATEGIES:
        raise ValueError("unknown strategy")
    unknown = set(relations) - set(RELATION_WEIGHTS)
    if unknown:
        raise ValueError("unknown relation")


def _seed_ids(conn: sqlite3.Connection, seeds: list[str]) -> list[str]:
    unique = sorted(set(seeds))[:SEED_CAP]
    if not unique:
        return []
    rows = conn.execute(
        f"SELECT id FROM notes WHERE id IN ({','.join('?' for _ in unique)}) "
        "AND status NOT IN ('tombstone','superseded') ORDER BY id",
        tuple(unique),
    ).fetchall()
    return [str(row[0]) for row in rows]


def traverse(
    conn: sqlite3.Connection,
    seeds: list[str],
    hops: int,
    relations: tuple[str, ...],
    direction: str,
    cap: int = VISITED_CAP,
) -> dict[str, tuple[int, list[str]]]:
    validate_query_params(hops, direction, 1, relations)
    if cap <= 0:
        return {}
    starts = _seed_ids(conn, seeds)
    if not starts or not relations:
        return {seed: (0, [seed]) for seed in starts[:cap]}
    # SQLite cannot deduplicate on nid while retaining depth inside one recursive
    # term. Build one bounded, breadth-first level per hop instead: each level
    # excludes all prior levels, so the cap counts unique visited nodes.
    seed_ph = ",".join("?" for _ in starts)
    params: list[object] = list(starts)
    ctes = [
        (
            "seed(nid) AS ("
            f"SELECT id FROM notes WHERE id IN ({seed_ph}) "
            "AND status NOT IN ('tombstone','superseded') ORDER BY id LIMIT ?)"
        ),
        "level_0(nid, depth) AS (SELECT nid, 0 FROM seed)",
    ]
    params.append(cap)
    previous = ["level_0"]
    for depth in range(1, hops + 1):
        previous_nodes = " UNION ALL ".join(f"SELECT nid FROM {name}" for name in previous)
        ctes.append(f"seen_{depth - 1}(nid) AS ({previous_nodes})")
        rel_ph = ",".join("?" for _ in relations)
        if direction == "out":
            join = f"JOIN level_{depth - 1} previous ON e.src = previous.nid"
            target = "e.dst"
        elif direction == "in":
            join = f"JOIN level_{depth - 1} previous ON e.dst = previous.nid"
            target = "e.src"
        else:
            join = f"JOIN level_{depth - 1} previous ON e.src = previous.nid OR e.dst = previous.nid"
            target = "CASE WHEN e.src = previous.nid THEN e.dst ELSE e.src END"
        ctes.append(
            f"level_{depth}(nid, depth) AS (SELECT DISTINCT {target}, {depth} "
            f"FROM edges e {join} WHERE e.relation IN ({rel_ph}) "
            f"AND {target} NOT IN (SELECT nid FROM seen_{depth - 1}) "
            "ORDER BY nid LIMIT (SELECT CASE WHEN ? > COUNT(*) THEN ? - COUNT(*) ELSE 0 END "
            f"FROM seen_{depth - 1}))"
        )
        params.extend(relations)
        params.extend((cap, cap))
        previous.append(f"level_{depth}")
    all_levels = " UNION ALL ".join(f"SELECT nid, depth FROM level_{depth}" for depth in range(hops + 1))
    ctes.append(f"walk(nid, depth) AS ({all_levels})")
    query = (
        "WITH RECURSIVE "
        + ", ".join(ctes)
        + " SELECT nid, MIN(depth) FROM walk JOIN notes ON notes.id = walk.nid "
        "WHERE notes.status NOT IN ('tombstone','superseded') "
        "GROUP BY nid ORDER BY MIN(depth), nid LIMIT ?"
    )
    params.append(cap)
    rows = conn.execute(query, tuple(params)).fetchall()
    return {str(nid): (int(depth), [str(nid)]) for nid, depth in rows}


def rrf(rankings: list[list[str]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, nid in enumerate(ranking, 1):
            scores[nid] = scores.get(nid, 0.0) + 1.0 / (RRF_K + rank)
    return scores


def ppr(
    conn: sqlite3.Connection,
    nodes: list[str],
    prior: dict[str, float],
    iterations: int = 20,
    alpha: float = 0.85,
) -> dict[str, float]:
    ordered = sorted(set(nodes))
    if not ordered:
        return {}
    idx = {nid: i for i, nid in enumerate(ordered)}
    teleport = [max(0.0, float(prior.get(nid, 0.0))) for nid in ordered]
    total = sum(teleport) or 1.0
    teleport = [value / total for value in teleport]
    adjacency: list[list[tuple[int, float]]] = [[] for _ in ordered]
    rows = conn.execute(
        f"SELECT src,dst,relation,confidence FROM edges WHERE src IN ({','.join('?' for _ in ordered)}) "
        f"AND dst IN ({','.join('?' for _ in ordered)}) ORDER BY src,dst,relation",
        tuple(ordered) * 2,
    ).fetchall()
    for src, dst, relation, confidence in rows:
        if relation not in RELATION_WEIGHTS:
            continue
        weight = RELATION_WEIGHTS[relation] * max(0.0, float(confidence))
        if weight:
            adjacency[idx[str(src)]].append((idx[str(dst)], weight))
    scores = teleport[:]
    for _ in range(iterations):
        nxt = [(1.0 - alpha) * value for value in teleport]
        for source, targets in enumerate(adjacency):
            mass = scores[source] * alpha
            total_out = sum(weight for _, weight in targets)
            if total_out == 0.0:
                for target, value in enumerate(teleport):
                    nxt[target] += mass * value
            else:
                for target, weight in targets:
                    nxt[target] += mass * weight / total_out
        scores = nxt
    return {nid: scores[i] for i, nid in enumerate(ordered)}


def _note_rows(conn: sqlite3.Connection, ids: list[str]) -> dict[str, tuple[str, str, str, str]]:
    if not ids:
        return {}
    rows = conn.execute(
        f"SELECT id,title,kind,body,source_sha256 FROM notes WHERE id IN ({','.join('?' for _ in ids)})",
        tuple(ids),
    ).fetchall()
    return {str(nid): (str(title), str(kind), str(body), str(source)) for nid, title, kind, body, source in rows}


def query(
    conn: sqlite3.Connection,
    vault: object | None,
    q: str,
    *,
    strategy: str = "adaptive",
    hops: int = 2,
    relations: tuple[str, ...] = ("causes", "depends_on", "related_to"),
    direction: str = "both",
    limit: int = 20,
    context: bool = False,
) -> dict[str, object]:
    validate_query_params(hops, direction, limit, relations, strategy)
    lexical = lexical_seed(conn, q, limit)
    vector = vector_seed(conn, q, limit) if strategy == "adaptive" else []
    seed_ranks: dict[str, dict[str, int | None]] = {
        "bm25": {nid: rank for rank, (nid, _score) in enumerate(lexical, 1)},
        "vector": {nid: rank for rank, (nid, _score) in enumerate(vector, 1)},
        "graph": {},
    }
    rankings = [[nid for nid, _score in lexical]]
    if vector:
        rankings.append([nid for nid, _score in vector])
    seeds = list(dict.fromkeys([nid for nid, _ in lexical] + [nid for nid, _ in vector]))
    graph = traverse(conn, seeds, hops, relations, direction) if strategy == "adaptive" and relations else {}
    if graph:
        rankings.append([nid for nid, (_depth, _paths) in sorted(graph.items(), key=lambda item: (item[1][0], item[0]))])
        seed_ranks["graph"] = {
            nid: rank for rank, (nid, (_depth, _paths)) in enumerate(sorted(graph.items(), key=lambda item: (item[1][0], item[0])), 1)
        }
    rrf_scores = rrf(rankings)
    node_ids = list(dict.fromkeys(seeds + list(graph)))
    ppr_scores = ppr(conn, node_ids, rrf_scores)
    notes = _note_rows(conn, node_ids)
    evidence: dict[str, list[str]] = {nid: [] for nid in notes}
    if notes:
        rows = conn.execute(
            f"SELECT src,dst,evidence FROM edges WHERE src IN ({','.join('?' for _ in notes)}) "
            f"OR dst IN ({','.join('?' for _ in notes)}) ORDER BY src,dst",
            tuple(notes) * 2,
        ).fetchall()
        for src, dst, item in rows:
            if item:
                if str(src) in evidence:
                    evidence[str(src)].append(str(item))
                if str(dst) in evidence:
                    evidence[str(dst)].append(str(item))
    ordered = sorted(notes, key=lambda nid: (-rrf_scores.get(nid, 0.0) - ppr_scores.get(nid, 0.0), nid))
    results: list[dict[str, object]] = []
    for nid in ordered[:limit]:
        title, kind, body, source = notes[nid]
        depth, paths = graph.get(nid, (0, [nid]))
        results.append(
            {
                "id": nid,
                "title": title,
                "kind": kind,
                "score": rrf_scores.get(nid, 0.0),
                "ppr_score": ppr_scores.get(nid, 0.0),
                "seed_ranks": {key: seed_ranks[key].get(nid) for key in ("bm25", "vector", "graph")},
                "depth": depth,
                "paths": paths,
                "sources": [source] if source else [],
                "evidence": sorted(set(evidence.get(nid, []))),
                "snippet": body,
                "path": f"notes/{kind}/{nid}.md",
            }
        )
    result: dict[str, object] = {
        "results": results,
        "strategy_used": strategy,
        "seed_counts": {"bm25": len(lexical), "vector": len(vector), "graph": len(graph)},
        "visited_count": len(graph) if graph else len(seeds),
    }
    if context:
        result["context"] = pack_context(conn, results)
    return result


def pack_context(conn: sqlite3.Connection, results: list[dict[str, object]], token_budget: int = 32000) -> str:
    if token_budget <= 0:
        raise ValueError("token_budget must be positive")
    parts: list[str] = []
    used = 0
    marker = "…[truncated]"
    for result in results:
        raw_sources = result.get("sources")
        raw_evidence = result.get("evidence")
        sources = ", ".join(str(item) for item in (raw_sources if isinstance(raw_sources, list) else [])) or "-"
        evidence = ", ".join(str(item) for item in (raw_evidence if isinstance(raw_evidence, list) else [])) or "-"
        prefix = (
            f"## {result.get('title', '')} ({result.get('id', '')})\n"
            f"source: {sources}\nevidence: {evidence}\n\n"
        )
        chunk = prefix + str(result.get("snippet", "")) + "\n"
        tokens = math.ceil(len(chunk) / 4)
        remaining = token_budget - used
        if tokens <= remaining:
            parts.append(chunk)
            used += tokens
            continue
        # One oversized result must not exceed the budget: hard-trim the snippet to
        # the remaining tokens and always append the marker.
        budget_chars = remaining * 4
        if len(marker) > budget_chars:
            parts.append(marker[:budget_chars])
            break
        payload = (prefix + str(result.get("snippet", "")))[: budget_chars - len(marker)]
        trimmed = payload + marker
        while trimmed and math.ceil(len(trimmed) / 4) > remaining:
            trimmed = trimmed[: len(trimmed) - 1]
        parts.append(trimmed)
        break
    return "\n".join(parts)
