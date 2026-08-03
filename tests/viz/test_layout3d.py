import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from kg.viz import layout3d


def test_fnv1a_known_vectors():
    assert layout3d.fnv1a("") == 2166136261
    assert layout3d.fnv1a("a") == (2166136261 ^ 97) * 16777619 % (2**32)


def test_fnv1a_matches_reference():
    assert layout3d.fnv1a("foo") == 2851307223
    assert layout3d.fnv1a("127.0.0.1") == 144953630


def test_lcg_sequence():
    assert layout3d.lcg_next(1) == (1 * 1103515245 + 12345) % (2**32)


def test_stellar_color_degree_bands():
    assert layout3d.stellar_color(0) == 0xFF6050
    assert layout3d.stellar_color(1) == 0xFF6050
    assert layout3d.stellar_color(6) == 0xFFC070
    assert layout3d.stellar_color(60) == 0x80A0FF


def test_size_for_label_constant():
    assert layout3d.size_for_label("anything") == 4.0


def test_layout_returns_exact_cbm_shape():
    nodes = [
        {"id": "nt_a", "kg_id": "nt_a", "label": "entity", "name": "Alpha"},
        {"id": "nt_b", "kg_id": "nt_b", "label": "entity", "name": "Beta"},
    ]
    edges = [{"source": "nt_a", "target": "nt_b", "type": "depends_on"}]
    r = layout3d.compute_layout(nodes, edges, max_nodes=2000)
    assert r["total_nodes"] == 2
    assert r["truncated_nodes"] == 0
    assert r["truncated_edges"] == 0
    assert len(r["nodes"]) == 2
    assert len(r["edges"]) == 1
    for n in r["nodes"]:
        assert set(n.keys()) == {"id", "kg_id", "x", "y", "z", "label", "name", "size", "color", "in_calls"}
        assert n["z"] == 0.0
        assert n["in_calls"] == 0
        assert n["size"] > 0
    e = r["edges"][0]
    assert set(e.keys()) == {"source", "target", "type"}
    assert e["type"] == "depends_on"


def test_layout_deterministic_same_process():
    nodes = [{"id": str(i), "kg_id": f"nt_{i}", "label": "entity", "name": f"N{i}"} for i in range(10)]
    edges = [{"source": f"nt_{i}", "target": f"nt_{(i+1)%10}", "type": "mentions"} for i in range(10)]
    a = layout3d.compute_layout(nodes, edges, max_nodes=2000)
    b = layout3d.compute_layout(nodes, edges, max_nodes=2000)
    assert a == b


def test_layout_finite_coordinates():
    nodes = [{"id": str(i), "kg_id": f"nt_{i}", "label": "entity", "name": f"N{i}"} for i in range(5)]
    r = layout3d.compute_layout(nodes, [], max_nodes=2000)
    for n in r["nodes"]:
        assert all(isinstance(n[k], float) and n[k] == n[k] for k in ("x", "y", "z"))


def test_max_nodes_truncation():
    nodes = [{"id": str(i), "kg_id": f"nt_{i}", "label": "entity", "name": f"N{i}"} for i in range(5)]
    edges = [{"source": f"nt_{i}", "target": f"nt_{(i+1)%5}", "type": "x"} for i in range(5)]
    r = layout3d.compute_layout(nodes, edges, max_nodes=3)
    assert len(r["nodes"]) == 3
    assert r["truncated_nodes"] == 2
    assert r["truncated_edges"] == 5  # all dropped input edges counted
    assert r["total_nodes"] == 5


def test_empty_layout():
    assert layout3d.compute_layout([], [], max_nodes=2000) == {
        "nodes": [],
        "edges": [],
        "total_nodes": 0,
        "truncated_nodes": 0,
        "truncated_edges": 0,
    }
