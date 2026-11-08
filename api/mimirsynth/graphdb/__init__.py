"""The graph database behind the brains, behind one interface (#357).

Every module reaches the graph through `db.graph()` / `db.list_graphs()` or through `backend()`, never through a driver of its own.
One backend per instance: today FalkorDB, where each brain is a graph of its own (a «partition»).

What a backend gives:
- `graph(name)`: a handle whose `query(cypher, params=None, timeout=None)` and `ro_query(...)` return a result with `header` and
  `result_set` (rows as lists, in the order of `RETURN`), which `db.rows()` turns into dicts.
- The partitions: list, copy (the snapshots before a merge, a brain renamed), delete.
- Graphiti's driver for one partition, so ingest and import build Graphiti on the same database.
- The Cypher that differs between databases: a vector literal and the cosine similarity of two vectors.
- What is informative and optional (version, memory) and the binary dump, which only some backends have.
- `value()`: a node, relationship or path of the driver as the neutral `Node` / `Edge` / `Path` below, for the Cypher console.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol


class Result(Protocol):
    header: list
    result_set: list[list]


class Graph(Protocol):
    def query(self, q: str, params: dict | None = None, timeout: int | None = None) -> Result: ...

    def ro_query(self, q: str, params: dict | None = None, timeout: int | None = None) -> Result: ...


@dataclass
class Node:
    id: str
    labels: list[str]
    properties: dict


@dataclass
class Edge:
    id: str
    relation: str
    source: str
    target: str
    properties: dict


@dataclass
class Path:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


class GraphBackend(ABC):
    name: str   # stable key: notifications, export manifests
    label: str  # what people read: «FalkorDB»

    @abstractmethod
    def graph(self, name: str) -> Graph: ...

    @abstractmethod
    def list_graphs(self) -> list[str]:
        """Every partition, the hidden ones («_» first: snapshots, scratch) included."""

    def exists(self, name: str) -> bool:
        return name in self.list_graphs()

    @abstractmethod
    def copy_graph(self, src: str, dst: str) -> None: ...

    @abstractmethod
    def delete_graph(self, name: str) -> None: ...

    @abstractmethod
    def graphiti_driver(self, name: str) -> Any:
        """A graphiti-core driver bound to the partition `name`; the caller closes it."""

    @abstractmethod
    def vector(self, expr: str) -> str:
        """Cypher that stores the list `expr` as a vector property."""

    @abstractmethod
    def cosine(self, a: str, b: str) -> str:
        """Cypher for the cosine similarity of two vectors, scaled to [0, 1] ((1 + cos) / 2)."""

    def value(self, v: Any) -> Any:
        """A driver value as `Node` / `Edge` / `Path`; anything else unchanged."""
        return v

    def version(self) -> dict:
        """Informative: what the server says it is. Empty when it does not answer."""
        return {}

    def memory(self) -> tuple[int, int] | None:
        """(used, limit) in bytes, when the database can tell."""
        return None

    def can_dump(self) -> bool:
        return False

    def dump(self, name: str) -> bytes:
        raise NotImplementedError(f"{self.label} has no binary dump")

    def restore(self, name: str, payload: bytes) -> None:
        raise NotImplementedError(f"{self.label} has no binary dump")


@lru_cache
def backend() -> GraphBackend:
    from ..config import settings
    from .falkor import FalkorBackend
    return FalkorBackend(settings.falkor_host, settings.falkor_port)
