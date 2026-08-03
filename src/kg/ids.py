import hashlib
import json
import re
import unicodedata
from typing import Any


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", title).strip()).casefold()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def note_id(kind: str, type: str | None, title: str) -> str:
    return "nt_" + _digest(f"{kind}|{type or ''}|{normalize_title(title)}")


def edge_id(src: str, relation: str, dst: str) -> str:
    return "eg_" + _digest(f"{src}|{relation}|{dst}")


def diff_id(content: Any) -> str:
    return "df_" + _digest(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
