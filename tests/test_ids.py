import json
import subprocess
import sys

from kg.ids import normalize_title, note_id, edge_id, diff_id


def test_normalization_and_prefixes() -> None:
    assert normalize_title("  Café   WORLD  ") == "café world"
    assert note_id("concept", None, "  Café WORLD ") == note_id("concept", None, "café world")
    assert note_id("concept", None, "x").startswith("nt_") and len(note_id("concept", None, "x")) == 19
    assert edge_id("nt_a", "causes", "nt_b").startswith("eg_")
    assert diff_id({"b": 1, "a": 2}).startswith("en_")
    assert diff_id({"b": 1, "a": 2}) == diff_id({"a": 2, "b": 1})


def test_cross_process_stability() -> None:
    code = "from kg.ids import note_id; print(note_id('fact','x',' Café  WORLD '))"
    a = subprocess.check_output([sys.executable, "-c", code], text=True).strip()
    b = subprocess.check_output([sys.executable, "-c", code], text=True).strip()
    assert a == b
