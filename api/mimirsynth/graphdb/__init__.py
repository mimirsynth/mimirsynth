"""The graph database behind the brains, behind one interface (#357).

Every module reaches the graph through `db.graph()` / `db.list_graphs()` or through `backend()`, never through a driver of its own.
One backend per instance, and each brain is a «partition» of it. The connection comes from the environment, from Administration → Graph
or, without either, it is the bundled FalkorDB (`graphconn.py`, #358); `reload()` switches to a new one without a restart.
- FalkorDB (`falkor.py`): a graph of its own per brain.
- Neo4j 5.26+ (`neo4j.py`): one database, where a brain is the nodes whose `group_id` is its name, as Graphiti already writes them.
  The Cypher the modules write is scoped to the partition by the backend, so it reads the same on both.

What a backend gives:
- `graph(name)`: a handle whose `query(cypher, params=None, timeout=None)` and `ro_query(...)` return a result with `header` and
  `result_set` (rows as lists, in the order of `RETURN`), which `db.rows()` turns into dicts.
- The partitions: list, copy (the snapshots before a merge, a brain renamed), delete.
- Graphiti's driver for one partition, so ingest and import build Graphiti on the same database.
- The Cypher that differs between databases: a vector literal and the cosine similarity of two vectors.
- What is informative and optional (version, memory) and the binary dump, which only some backends have.
- `value()`: a node, relationship or path of the driver as the neutral `Node` / `Edge` / `Path` below, for the Cypher console.
- `check_console()`: what the read-only Cypher console refuses to run (`Unscopable`). Only a shared database refuses anything.
"""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

BACKENDS = {"falkordb": "FalkorDB", "neo4j": "Neo4j"}
DEFAULT_PORTS = {"falkordb": 6379, "neo4j": 7687}


@dataclass(frozen=True)
class Connection:
    """Where the graph database is and how to sign in to it. `uri` is Neo4j's as the environment gives it; without it, it is built from
    host, port and TLS."""
    backend: str
    host: str = ""
    port: int = 0
    user: str = ""
    password: str = field(default="", repr=False)
    tls: bool = False
    database: str = ""
    uri: str = ""

    @property
    def label(self) -> str:
        return BACKENDS.get(self.backend, self.backend)

    def neo4j_uri(self) -> str:
        return self.uri or f"{'bolt+s' if self.tls else 'bolt'}://{self.host}:{self.port or DEFAULT_PORTS['neo4j']}"

    def address(self) -> str:
        """What people read: host:port, or Neo4j's URI."""
        return self.neo4j_uri() if self.backend == "neo4j" else f"{self.host}:{self.port or DEFAULT_PORTS['falkordb']}"


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


class Unscopable(ValueError):
    """A query a backend cannot keep inside one brain, refused rather than run (#389). `code` says why: «pattern», «varlength»,
    «comment», «param», «char», «function», «call» or «write»; `detail` is the part of the query concerned."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail


class GraphBackend(ABC):
    name: str   # stable key: notifications, export manifests
    label: str  # what people read: «FalkorDB»
    shared_database = False  # True: the brains share one database and the backend scopes each query to one brain (Neo4j)

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

    def check_console(self, q: str) -> None:
        """Raises `Unscopable` when the read-only Cypher console must not run `q`. A backend with a graph per brain has nothing to
        refuse: a query cannot leave its graph."""

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

    def close(self) -> None:
        """Lets go of the driver's connections; the backend is not used after this."""


def make(conn: Connection) -> GraphBackend:
    """The backend for a connection, without connecting yet."""
    if conn.backend == "neo4j":
        from .neo4j import Neo4jBackend
        return Neo4jBackend(conn.neo4j_uri(), conn.user or "neo4j", conn.password, conn.database or None)  # compose passes an empty user
    if conn.backend != "falkordb":
        raise ValueError(f"graph backend {conn.backend!r}: it must be «falkordb» or «neo4j»")
    from .falkor import FalkorBackend
    return FalkorBackend(conn.host, conn.port or DEFAULT_PORTS["falkordb"], conn.user or None, conn.password or None, tls=conn.tls)


@lru_cache
def backend() -> GraphBackend:
    """The instance's backend, built once from the connection in force (`graphconn.current`). A failure to read that connection (the
    control database down) is raised and not kept: the next call tries again."""
    from ..graphconn import current
    return make(current()[0])


CLOSE_AFTER = 60.0  # seconds the old backend stays open after a reload, for the queries that were already running on it


def reload() -> None:
    """Uses the connection in force from the next call on. The old backend is closed a minute later, once what was running on it ended.
    One process per instance (the container runs one uvicorn worker), so clearing the cache here reaches every request."""
    old = backend() if backend.cache_info().currsize else None
    backend.cache_clear()
    if old is not None:
        def _close():
            try:
                old.close()
            except Exception:  # noqa: BLE001  (closing is best effort)
                logging.getLogger("mimirsynth").debug("closing the previous graph backend failed", exc_info=True)
        t = threading.Timer(CLOSE_AFTER, _close)
        t.daemon = True
        t.start()
