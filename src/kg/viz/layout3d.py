"""Deterministic CBM-compatible 3D force layout."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import TypedDict

BH_THETA = 1.2
OCTREE_MAX_DEPTH = 26
OCTREE_MIN_HALF = 1e-4
LOCAL_REPULSION = 8.0
LOCAL_ATTRACTION = 1.0
LOCAL_ANCHOR_K = 0.25
LOCAL_ITERATIONS = 40
JITTER = 40.0
Z_DEPTH = 0.0
FNV_OFFSET = 2166136261
FNV_PRIME = 16777619
MASK32 = 0xFFFFFFFF
MAX_NODES = 2000
MAX_EDGES = 4000


class LayoutResult(TypedDict):
    nodes: list[dict[str, object]]
    edges: list[dict[str, str]]
    total_nodes: int
    truncated_nodes: int
    truncated_edges: int


def fnv1a(s: str) -> int:
    h = FNV_OFFSET
    for b in s.encode("utf-8"):
        h = ((h ^ b) * FNV_PRIME) & MASK32
    return h


def lcg_next(seed: int) -> int:
    return (seed * 1103515245 + 12345) & MASK32


def rand_float(seed: int) -> float:
    seed = lcg_next(seed)
    return ((seed >> 16) & 0x7FFF) / 32768.0 - 0.5


def stellar_color(degree: int) -> int:
    if degree <= 1:
        return 0xFF6050
    if degree <= 3:
        return 0xFF8855
    if degree <= 5:
        return 0xFFA060
    if degree <= 8:
        return 0xFFC070
    if degree <= 12:
        return 0xFFE080
    if degree <= 18:
        return 0xFFF0C0
    if degree <= 25:
        return 0xFFF8E8
    if degree <= 35:
        return 0xE8E8FF
    if degree <= 50:
        return 0xC0D0FF
    return 0x80A0FF


def size_for_label(label: str) -> float:
    return {
        "Project": 20.0,
        "Package": 15.0,
        "Module": 15.0,
        "Folder": 12.0,
        "File": 8.0,
        "Class": 6.0,
        "Struct": 6.0,
        "Interface": 6.0,
        "Function": 4.0,
        "Method": 4.0,
    }.get(label, 4.0)


def cluster_key(path: str) -> str:
    return "/".join(path.split("/")[:3])


def _f32(value: float) -> float:
    """Round-trip a float through IEEE-754 binary32 to mirror upstream C float.

    Upstream layout3d.c computes with ``float`` (``sqrtf``/``cosf``, ``float``
    struct fields). Doubles alone can pull away from the reference bit pattern;
    rounding each stored value to float32 keeps the port bit-comparable.
    """
    return float(struct.unpack("<f", struct.pack("<f", value))[0])


@dataclass
class _Body:
    x: float
    y: float
    z: float
    ax: float
    ay: float
    az: float
    mass: float
    fx: float = 0.0
    fy: float = 0.0
    fz: float = 0.0


class _Octree:
    def __init__(self, ox: float, oy: float, oz: float, half: float) -> None:
        self.ox, self.oy, self.oz, self.half = ox, oy, oz, half
        self.cx = self.cy = self.cz = 0.0
        self.total_mass = 0.0
        self.body_index = -1
        self.body_mass = 0.0
        self.children: list[_Octree | None] = [None] * 8

    def _octant(self, x: float, y: float, z: float) -> int:
        return (1 if x >= self.ox else 0) | (2 if y >= self.oy else 0) | (4 if z >= self.oz else 0)

    def _child_center(self, o: int) -> tuple[float, float, float]:
        q = self.half * 0.5
        return (
            self.ox + (q if o & 1 else -q),
            self.oy + (q if o & 2 else -q),
            self.oz + (q if o & 4 else -q),
        )

    def _insert_child(self, o: int, idx: int, x: float, y: float, z: float, mass: float, depth: int) -> None:
        child = self.children[o]
        if child is None:
            child = _Octree(*self._child_center(o), self.half * 0.5)
            self.children[o] = child
        child.insert(idx, x, y, z, mass, depth + 1)

    def insert(self, idx: int, x: float, y: float, z: float, mass: float, depth: int = 0) -> None:
        if self.total_mass == 0.0 and self.body_index == -1:
            self.body_index, self.body_mass = idx, mass
            self.cx, self.cy, self.cz, self.total_mass = x, y, z, mass
            return
        if depth >= OCTREE_MAX_DEPTH or self.half < OCTREE_MIN_HALF:
            nm = self.total_mass + mass
            self.cx = _f32((self.cx * self.total_mass + x * mass) / nm)
            self.cy = _f32((self.cy * self.total_mass + y * mass) / nm)
            self.cz = _f32((self.cz * self.total_mass + z * mass) / nm)
            self.total_mass, self.body_index = nm, -1
            return
        if self.body_index >= 0:
            old = self.body_index
            ox, oy, oz, om = self.cx, self.cy, self.cz, self.body_mass
            self.body_index = -1
            self._insert_child(self._octant(ox, oy, oz), old, ox, oy, oz, om, depth)
        nm = self.total_mass + mass
        self.cx = _f32((self.cx * self.total_mass + x * mass) / nm)
        self.cy = _f32((self.cy * self.total_mass + y * mass) / nm)
        self.cz = _f32((self.cz * self.total_mass + z * mass) / nm)
        self.total_mass = nm
        self._insert_child(self._octant(x, y, z), idx, x, y, z, mass, depth)

    def repulse(self, px: float, py: float, pz: float, mm: float, idx: int, kr: float, acc: list[float]) -> None:
        if self.total_mass == 0.0 or self.body_index == idx:
            return
        dx, dy, dz = px - self.cx, py - self.cy, pz - self.cz
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if self.body_index >= 0 or (self.half * 2.0 / (d + 0.001)) < BH_THETA:
            d = max(d, 0.01)
            f = kr * mm * self.total_mass / d
            acc[0] += f * dx / d
            acc[1] += f * dy / d
            acc[2] += f * dz / d
            return
        for child in self.children:
            if child is not None:
                child.repulse(px, py, pz, mm, idx, kr, acc)


def _local_optimize(bodies: list[_Body], edge_sources: list[int], edge_targets: list[int]) -> None:
    iterations = LOCAL_ITERATIONS
    if len(bodies) > 500_000:
        iterations = 10
    elif len(bodies) > 100_000:
        iterations = 20
    for _ in range(iterations):
        for body in bodies:
            body.fx = body.fy = body.fz = 0.0
        if not bodies:
            continue
        xs, ys, zs = zip(*((b.x, b.y, b.z) for b in bodies))
        mnx, mxx = min(xs), max(xs)
        mny, mxy = min(ys), max(ys)
        mnz, mxz = min(zs), max(zs)
        half = max(mxx - mnx, mxy - mny, mxz - mnz) * 0.5 + 1.0
        root = _Octree((mnx + mxx) * 0.5, (mny + mxy) * 0.5, (mnz + mxz) * 0.5, half)
        for i, body in enumerate(bodies):
            root.insert(i, body.x, body.y, body.z, body.mass)
        for i, body in enumerate(bodies):
            acc = [0.0, 0.0, 0.0]
            root.repulse(body.x, body.y, body.z, body.mass, i, LOCAL_REPULSION, acc)
            body.fx, body.fy, body.fz = acc
        for s, t in zip(edge_sources, edge_targets):
            dx, dy, dz = bodies[t].x - bodies[s].x, bodies[t].y - bodies[s].y, bodies[t].z - bodies[s].z
            bodies[s].fx += dx * LOCAL_ATTRACTION
            bodies[s].fy += dy * LOCAL_ATTRACTION
            bodies[s].fz += dz * LOCAL_ATTRACTION
            bodies[t].fx -= dx * LOCAL_ATTRACTION
            bodies[t].fy -= dy * LOCAL_ATTRACTION
            bodies[t].fz -= dz * LOCAL_ATTRACTION
        for body in bodies:
            body.fx += (body.ax - body.x) * LOCAL_ANCHOR_K * body.mass
            body.fy += (body.ay - body.y) * LOCAL_ANCHOR_K * body.mass
            body.fz += (body.az - body.z) * LOCAL_ANCHOR_K * body.mass
        for body in bodies:
            fm = math.sqrt(body.fx * body.fx + body.fy * body.fy + body.fz * body.fz)
            speed = min(1.0, 8.0 / (fm + 0.001))
            body.x += body.fx * speed
            body.y += body.fy * speed
            body.z += body.fz * speed


def compute_layout(nodes: list[dict], edges: list[dict], max_nodes: int = MAX_NODES) -> LayoutResult:
    max_nodes = max(1, min(int(max_nodes), MAX_NODES))
    total = len(nodes)
    selected = sorted(nodes, key=lambda n: str(n["id"]))[:max_nodes]
    idset = {str(n["id"]) for n in selected}
    filtered = [e for e in edges if str(e.get("source")) in idset and str(e.get("target")) in idset]
    mapped = filtered[:MAX_EDGES]
    deg: dict[str, int] = {}
    for edge in mapped:
        deg[str(edge["source"])] = deg.get(str(edge["source"]), 0) + 1
        deg[str(edge["target"])] = deg.get(str(edge["target"]), 0) + 1
    idx = {str(n["id"]): i for i, n in enumerate(selected)}
    bodies: list[_Body] = []
    for node in selected:
        node_id = str(node["id"])
        h = fnv1a(cluster_key(str(node.get("path", ""))))
        angle = _f32((h & 0xFFFF) / 65535.0 * 6.2832)
        radius = _f32(500.0 + ((h >> 16) & 0xFF) / 255.0 * 250.0)
        seed = fnv1a(node_id)
        x = _f32(radius * math.cos(angle) + rand_float(seed) * JITTER)
        y = _f32(radius * math.sin(angle) + rand_float(seed) * JITTER)
        bodies.append(_Body(x, y, Z_DEPTH, x, y, Z_DEPTH, float(deg.get(node_id, 0) + 1)))
    sources = [idx[str(e["source"])] for e in mapped]
    targets = [idx[str(e["target"])] for e in mapped]
    _local_optimize(bodies, sources, targets)
    out_nodes = []
    for i, node in enumerate(selected):
        node_id = str(node["id"])
        degree = deg.get(node_id, 0)
        out_nodes.append(
            {
                "id": node_id,
                "kg_id": str(node.get("kg_id", node_id)),
                "x": float(round(bodies[i].x, 6)),
                "y": float(round(bodies[i].y, 6)),
                "z": 0.0,
                "label": str(node.get("label", "")),
                "name": str(node.get("name", "")),
                "size": float(round(size_for_label(str(node.get("label", ""))) + (min(degree * 0.3, 10.0) if degree > 5 else 0.0), 6)),
                "color": f"#{stellar_color(degree):06x}",
                "in_calls": 0,
            }
        )
    out_nodes.sort(key=lambda n: str(n["id"]))
    out_edges = [
        {"source": str(e["source"]), "target": str(e["target"]), "type": str(e.get("type", ""))}
        for e in sorted(mapped, key=lambda e: (str(e["source"]), str(e["target"]), str(e.get("type", ""))))
    ]
    return {
        "nodes": out_nodes,
        "edges": out_edges,
        "total_nodes": total,
        "truncated_nodes": total - len(selected),
        "truncated_edges": len(edges) - len(mapped),
    }
