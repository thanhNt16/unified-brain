import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"


def _script():
    return (
        f"import sys; sys.path.insert(0, {str(SRC)!r}); "
        "from kg.viz import layout3d; "
        "nodes=[{'id':str(i),'kg_id':'nt_'+str(i),'label':'entity','name':'N'+str(i)} for i in range(30)]; "
        "edges=[{'source':'nt_'+str(i),'target':'nt_'+str((i+1)%30),'type':'mentions'} for i in range(30)]; "
        "import json as j; print(j.dumps(layout3d.compute_layout(nodes, edges, 2000), sort_keys=True))"
    )


def test_layout_deterministic_across_processes():
    out1 = subprocess.check_output([sys.executable, "-c", _script()], cwd=str(REPO)).decode()
    out2 = subprocess.check_output([sys.executable, "-c", _script()], cwd=str(REPO)).decode()
    assert out1 == out2


def test_hard_caps():
    nodes = [{"id": f"nt_{i:04d}", "kg_id": f"nt_{i:04d}", "label": "entity", "name": f"N{i}"} for i in range(2500)]
    edges = [
        {"source": f"nt_{i % 2000:04d}", "target": f"nt_{(i + 7) % 2000:04d}", "type": "mentions"}
        for i in range(4500)
    ]
    sys.path.insert(0, str(SRC))
    from kg.viz import layout3d

    r = layout3d.compute_layout(nodes, edges, 2000)
    assert len(r["nodes"]) == 2000
    assert len(r["edges"]) == 4000
    assert r["truncated_nodes"] == 500
    assert r["truncated_edges"] == 500
    assert r["total_nodes"] == 2500


def test_layout_payload_under_4_mib():
    nodes = [{"id": str(i), "kg_id": f"nt_{i}", "label": "entity", "name": f"N{i}"} for i in range(2000)]
    edges = [{"source": f"nt_{i}", "target": f"nt_{(i+1)%2000}", "type": "mentions"} for i in range(4000)]
    sys.path.insert(0, str(SRC))
    from kg.viz import layout3d

    r = layout3d.compute_layout(nodes, edges, 2000)
    data = json.dumps(r, allow_nan=False).encode()
    assert len(data) <= 4 * 1024 * 1024
