from __future__ import annotations

import math
import re
import zlib
from collections import defaultdict
from typing import Final

DIM: Final[int] = 16384
_WORD = re.compile(r"[a-z0-9]+")


def extract(text: str) -> dict[int, float]:
    words = _WORD.findall(text.lower())
    trigrams: list[str] = []
    for word in words:
        padded = f"#{word}#"
        for i in range(len(padded) - 2):
            trigrams.append(padded[i : i + 3])
    vec: dict[int, float] = defaultdict(float)
    for word in words:
        vec[zlib.crc32(word.encode()) % DIM] += 1.0
    for trigram in trigrams:
        bucket = zlib.crc32(trigram.encode()) % DIM
        sign = 1.0 if (zlib.crc32(trigram.encode()) & 1) == 0 else -1.0
        vec[bucket] += sign
    return {feature: weight for feature, weight in vec.items() if weight}


def l2(vec: dict[int, float]) -> float:
    return math.sqrt(sum(value * value for value in vec.values()))


def cosine(a: dict[int, float], b: dict[int, float], b_norm: float | None = None) -> float:
    an = l2(a)
    bn = b_norm if b_norm is not None else l2(b)
    if an == 0.0 or bn == 0.0:
        return 0.0
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    dot = sum(value * large.get(feature, 0.0) for feature, value in small.items())
    return dot / (an * bn)
