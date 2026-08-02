from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Relation(str, Enum):
    depends_on = "depends_on"
    causes = "causes"
    supports = "supports"
    contradicts = "contradicts"
    supersedes = "supersedes"
    mentions = "mentions"
    related_to = "related_to"


class NoteStatus(str, Enum):
    draft = "draft"
    verified = "verified"
    superseded = "superseded"
    tombstone = "tombstone"


class Provenance(Strict):
    source_sha256: str = Field(min_length=64, max_length=64)
    method: str = Field(min_length=1)
    locator: str | None = None


class Note(Strict):
    id: str = Field(pattern=r"^nt_[0-9a-f]{16}$")
    kind: Literal["entity", "concept", "fact", "source", "summary"]
    type: str | None = Field(default=None, pattern=r"^[a-z0-9_]+$")
    title: str = Field(min_length=1)
    created: str = Field(min_length=1)
    updated: str = Field(min_length=1)
    status: NoteStatus = NoteStatus.draft
    supersedes: str | None = None
    source_sha256: str = Field(min_length=64, max_length=64)
    refs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    provenance: list[Provenance] = Field(default_factory=list)
    embedding: dict[str, str | int | float] | None = None
    body: str = ""


class Edge(Strict):
    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)
    relation: Relation
    confidence: float = Field(ge=0, le=1)
    evidence: str | None = None


class Proposal(Strict):
    schema_version: int = Field(ge=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    notes: list[Note] = Field(default_factory=list, max_length=500)
    edges: list[Edge] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def unique_note_ids(self) -> "Proposal":
        ids = [n.id for n in self.notes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate note id")
        return self


class DreamOp(Strict):
    op: Literal["drop", "supersede"]
    id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    pass_name: Literal["dedup", "contradiction", "supersede", "stale", "orphan", "open-q", "community"]


class ProposedDiff(Strict):
    id: str = Field(pattern=r"^df_[0-9a-f]{16}$")
    status: Literal["proposed", "approved", "rejected"]
    operations: list[DreamOp] = Field(default_factory=list, max_length=500)
