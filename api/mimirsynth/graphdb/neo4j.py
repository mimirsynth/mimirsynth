"""Neo4j 5.26+: one database, where a brain is the nodes whose `group_id` is its name.

Graphiti already writes a `group_id` on every node and relationship and filters its own queries by it, so ingest, search and
the indices work unchanged on one database. What the modules write themselves (`db.graph(name).query(...)`) was written for
FalkorDB, where a brain is a graph of its own and `MATCH (n:Entity)` only sees that brain. Here the handle scopes that Cypher to
the partition before running it (`scope()`): every node pattern a query reads gets `group_id: $partition`, and every node a
query creates with a label or properties gets it too. A relationship is in a brain when its two ends are.

The same applies to Community and Enterprise: one database (`MIMIRSYNTH_NEO4J_DATABASE`, or the server's default). A database
per brain on Enterprise would need its own names (Neo4j's rules are stricter than a brain's slug), its own copy and its own
export; one model for both editions keeps snapshots, export, import and the Cypher the same. `version()` says which edition
answered.

Values: Graphiti stores dates as Neo4j temporals here and as ISO-8601 strings on FalkorDB, and the modules compare, sort and parse
them as those strings. So results come back with temporals as ISO strings, and parameters that are ISO-8601 datetimes with a
zone go in as datetimes, which compare with what Graphiti stored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cached_property
from typing import Any

from . import Edge, GraphBackend, Node, Path

PARTITION = "mimirsynth_partition"  # the parameter the scoped Cypher reads the partition from
BATCH = 1000

# --- scoping the Cypher written for one graph per brain ---------------------------------------------------------------------

_IDENT = r"(?:`[^`]*`|[A-Za-z_][A-Za-z0-9_]*)"
_NODE = re.compile(rf"^\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)?\s*(?P<labels>(?::\s*!?\s*{_IDENT}\s*(?:[|&]\s*!?\s*{_IDENT}\s*)*)*)(?P<rest>.*)$", re.S)
_CLAUSES = {"MATCH", "MERGE", "CREATE", "WHERE", "RETURN", "WITH", "SET", "DELETE", "DETACH", "REMOVE", "UNWIND", "ORDER", "LIMIT",
            "SKIP", "CALL", "UNION", "FOREACH", "YIELD", "ON"}
_WRITES = {"CREATE", "MERGE"}
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:?\d{2})?$")  # a datetime; without a zone, UTC


def _skip_quoted(q: str, i: int) -> int:
    """The index after the string or backtick name that starts at `i`."""
    quote, j = q[i], i + 1
    while j < len(q):
        if q[j] == "\\" and quote != "`":
            j += 2
            continue
        if q[j] == quote:
            if quote == "`" and q[j + 1:j + 2] == "`":  # `` inside a name
                j += 2
                continue
            return j + 1
        j += 1
    return j


def _matching(q: str, i: int, open_: str, close: str) -> int:
    """The index of the bracket that closes the one at `i`, or -1."""
    depth, j = 0, i
    while j < len(q):
        c = q[j]
        if c in "'\"`":
            j = _skip_quoted(q, j)
            continue
        if c == open_:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _node(inner: str) -> tuple[str, str, str] | None:
    """(variable, labels, map) when `inner` reads as the inside of a node pattern."""
    m = _NODE.match(inner)
    if not m:
        return None
    var, labels, rest = m["var"] or "", m["labels"] or "", m["rest"].strip()
    if rest and not (rest[0] == "{" and _matching(rest, 0, "{", "}") == len(rest) - 1):
        return None
    if not (var or labels or rest) and inner.strip():
        return None
    return var, labels, rest


def _with_partition(inner: str, labels: str, props: str) -> str:
    key = f"group_id: ${PARTITION}"
    if props:  # last: a key repeated in a map keeps its last value, so a `group_id` of the query's own cannot leave the partition
        start = inner.rindex(props)
        body = props[1:-1].strip()
        return inner[:start] + ("{" + key + "}" if not body else props[:-1].rstrip() + ", " + key + "}") + inner[start + len(props):]
    return inner.rstrip() + (" " if inner.strip() else "") + "{" + key + "}"


def _next_sig(q: str, i: int) -> str:
    while i < len(q) and q[i].isspace():
        i += 1
    return q[i:i + 2]


def scope(q: str) -> str:
    """The Cypher `q`, with its node patterns scoped to the partition in `$mimirsynth_partition` (see the module's docstring)."""
    out, sig, ctx, i, n = [], [], [None], 0, len(q)
    while i < n:
        c = q[i]
        if c in "'\"`":
            j = _skip_quoted(q, i)
            lit = q[i:j]
            out.append(f"datetime({lit})" if c != "`" and _ISO.match(lit[1:-1]) else lit)  # as a parameter would go in
            sig.append("lit")
            i = j
            continue
        if q.startswith("//", i):
            j = q.find("\n", i)
            j = n if j < 0 else j
            out.append(q[i:j])
            i = j
            continue
        if q.startswith("/*", i):
            j = q.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(q[i:j])
            i = j
            continue
        if c.isalpha() or c == "_":
            m = re.compile(r"[A-Za-z_][A-Za-z0-9_]*").match(q, i)
            word = m.group(0)
            if word.upper() in _CLAUSES:
                ctx[-1] = word.upper()
            out.append(word)
            sig.append(("w", word.upper()))
            i = m.end()
            continue
        if c == "$":
            m = re.compile(r"\$[A-Za-z0-9_]*").match(q, i)
            out.append(m.group(0))
            sig.append("lit")
            i = m.end()
            continue
        if c == "{":
            ctx.append(None)
        elif c == "}" and len(ctx) > 1:
            ctx.pop()
        if c == "(":
            close = _matching(q, i, "(", ")")
            node = _node(q[i + 1:close]) if close > 0 else None
            if node and _is_pattern(sig, ctx[-1], _next_sig(q, close + 1)):
                inner = q[i + 1:close]
                var, labels, props = node
                if ctx[-1] not in _WRITES or labels or props:
                    inner = _with_partition(inner, labels, props)
                out.append("(" + inner + ")")
                sig.append(")")
                i = close + 1
                continue
        out.append(c)
        if not c.isspace():
            sig.append(c)
        i += 1
    return "".join(out)


def _is_pattern(sig: list, clause: str | None, after: str) -> bool:
    prev = sig[-1] if sig else None
    prev2 = sig[-2] if len(sig) > 1 else None
    if prev in (("w", "MATCH"), ("w", "MERGE"), ("w", "CREATE"), "{"):  # «{»: `EXISTS { (n) }`, `COUNT { (n) }`
        return True
    if prev == "," and clause in ("MATCH", "MERGE", "CREATE"):
        return True
    if prev == "-" and prev2 in ("]", "-", ")", "<"):
        return True
    if prev == ">" and prev2 == "-":
        return True
    return after[:1] == "-" and after[1:2] in ("[", "-", ">") or after == "<-"


# --- values ------------------------------------------------------------------------------------------------------------------


def _param(v: Any) -> Any:
    """An ISO-8601 datetime as a datetime, so it compares with the temporals Graphiti stores; lists and maps inside."""
    if isinstance(v, str) and _ISO.match(v):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return v
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)  # Graphiti's dates are UTC, and a date with a zone does not compare with one without
    if isinstance(v, list):
        return [_param(x) for x in v]
    if isinstance(v, tuple):
        return tuple(_param(x) for x in v)
    if isinstance(v, dict):
        return {k: _param(x) for k, x in v.items()}
    return v


def _out(v: Any) -> Any:
    """A Neo4j value as the modules read it on FalkorDB: temporals as ISO-8601, graph values as `Node` / `Edge` / `Path`."""
    from neo4j import graph as ng
    from neo4j import time as nt
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, list):
        return [_out(x) for x in v]
    if isinstance(v, dict):
        return {k: _out(x) for k, x in v.items()}
    if isinstance(v, nt.DateTime):
        return v.to_native().isoformat()
    if isinstance(v, (nt.Date, nt.Time)):
        return v.iso_format()
    if isinstance(v, nt.Duration):
        return str(v)
    if isinstance(v, ng.Node):
        return Node(v.element_id, list(v.labels), {k: _out(x) for k, x in v.items()})
    if isinstance(v, ng.Relationship):
        return Edge(v.element_id, v.type, v.start_node.element_id, v.end_node.element_id, {k: _out(x) for k, x in v.items()})
    if isinstance(v, ng.Path):
        return Path([_out(x) for x in v.nodes], [_out(x) for x in v.relationships])
    return v


@dataclass
class Result:
    header: list
    result_set: list[list]


class Neo4jGraph:
    """One brain: Cypher written for a graph of its own, run scoped to the brain's partition."""

    def __init__(self, b: Neo4jBackend, name: str):
        self.backend, self.name = b, name

    def _run(self, q: str, params: dict | None, timeout: int | None, read: bool) -> Result:
        from neo4j import Query
        from neo4j import READ_ACCESS, WRITE_ACCESS
        p = {k: _param(v) for k, v in (params or {}).items()}
        p[PARTITION] = self.name
        query = Query(scope(q), timeout=(timeout / 1000) if timeout else None)  # FalkorDB's timeouts are in milliseconds
        with self.backend.driver.session(database=self.backend.database,
                                         default_access_mode=READ_ACCESS if read else WRITE_ACCESS) as s:
            res = s.run(query, p)
            rows = [[self._own(_out(x)) for x in r.values()] for r in res]
            return Result(list(res.keys()), rows)

    def _own(self, v: Any) -> Any:
        """Refuses a node or relationship of another brain: what scoping cannot see (a procedure's results) does not leak."""
        if isinstance(v, (Node, Edge)) and v.properties.get("group_id", self.name) != self.name:
            raise PermissionError("the query reached a node or relationship outside this brain")
        if isinstance(v, Path):
            for x in (*v.nodes, *v.edges):
                self._own(x)
        elif isinstance(v, list):
            for x in v:
                self._own(x)
        elif isinstance(v, dict):
            for x in v.values():
                self._own(x)
        return v

    def query(self, q: str, params: dict | None = None, timeout: int | None = None) -> Result:
        return self._run(q, params, timeout, read=False)

    def ro_query(self, q: str, params: dict | None = None, timeout: int | None = None) -> Result:
        return self._run(q, params, timeout, read=True)


class Neo4jBackend(GraphBackend):
    name = "neo4j"
    label = "Neo4j"
    shared_database = True

    def __init__(self, uri: str, user: str, password: str, database: str | None = None):
        if not uri:
            raise ValueError("the Neo4j backend needs a URI (MIMIRSYNTH_NEO4J_URI=bolt://host:7687, or Administration → Graph)")
        self.uri, self.user, self.password, self._database = uri, user, password, database

    @cached_property
    def driver(self):
        from neo4j import GraphDatabase
        return GraphDatabase.driver(self.uri, auth=(self.user, self.password) if self.user else None, notifications_min_severity="OFF")

    @cached_property
    def database(self) -> str:
        """The configured database or, without one, the server's default: Graphiti's driver needs it by name."""
        if self._database:
            return self._database
        records, _, _ = self.driver.execute_query("CALL db.info() YIELD name RETURN name")
        return records[0]["name"]

    def _run(self, q: str, params: dict | None = None, read: bool = False) -> list:
        """Cypher on the whole database, unscoped and with the driver's own values: the partitions themselves."""
        from neo4j import READ_ACCESS, WRITE_ACCESS
        with self.driver.session(database=self.database, default_access_mode=READ_ACCESS if read else WRITE_ACCESS) as s:
            return list(s.run(q, params or {}))

    def graph(self, name: str) -> Neo4jGraph:
        return Neo4jGraph(self, name)

    def list_graphs(self) -> list[str]:
        rows = self._run("MATCH (n) WHERE n.group_id IS NOT NULL RETURN DISTINCT n.group_id AS g", read=True)
        return sorted(r["g"] for r in rows if isinstance(r["g"], str))

    def exists(self, name: str) -> bool:
        return bool(self._run("MATCH (n {group_id: $g}) RETURN 1 AS x LIMIT 1", {"g": name}, read=True))

    def copy_graph(self, src: str, dst: str) -> None:
        """Copies the nodes and relationships of `src` under `dst`, with `group_id` rewritten, in batches."""
        if self.exists(dst):
            raise ValueError(f"the graph {dst!r} already exists")
        ids: dict[str, str] = {}
        nodes = self._run("MATCH (n {group_id: $s}) RETURN elementId(n) AS k, labels(n) AS l, properties(n) AS p", {"s": src}, read=True)
        for i in range(0, len(nodes), BATCH):
            rows = [{"k": r["k"], "l": r["l"], "p": {**r["p"], "group_id": dst}} for r in nodes[i:i + BATCH]]
            for r in self._run("UNWIND $rows AS row CREATE (m) SET m = row.p SET m:$(row.l) RETURN row.k AS k, elementId(m) AS e",
                               {"rows": rows}):
                ids[r["k"]] = r["e"]
        rels = self._run("MATCH (a {group_id: $s})-[r]->(b {group_id: $s}) RETURN elementId(a) AS a, elementId(b) AS b, type(r) AS t, "
                         "properties(r) AS p", {"s": src}, read=True)
        for i in range(0, len(rels), BATCH):
            rows = [{"a": ids[r["a"]], "b": ids[r["b"]], "t": r["t"],
                     "p": {**r["p"], "group_id": dst} if "group_id" in r["p"] else dict(r["p"])} for r in rels[i:i + BATCH]]
            self._run("UNWIND $rows AS row MATCH (a) WHERE elementId(a) = row.a MATCH (b) WHERE elementId(b) = row.b "
                      "CREATE (a)-[r:$(row.t)]->(b) SET r = row.p", {"rows": rows})

    def delete_graph(self, name: str) -> None:
        with self.driver.session(database=self.database) as s:
            s.run("MATCH (n {group_id: $g}) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 5000 ROWS", {"g": name}).consume()

    def graphiti_driver(self, name: str):
        """Graphiti on the one database; the brain is the `group_id` the caller passes to Graphiti (ingest does)."""
        from graphiti_core.driver.neo4j_driver import Neo4jDriver
        return Neo4jDriver(self.uri, self.user, self.password, database=self.database)

    def vector(self, expr: str) -> str:
        return expr  # a list of floats, as Graphiti stores the embeddings here

    def cosine(self, a: str, b: str) -> str:
        return f"vector.similarity.cosine({a}, {b})"  # already (1 + cos) / 2

    def value(self, v: Any) -> Any:
        return _out(v)

    def close(self) -> None:
        if "driver" in self.__dict__:
            self.driver.close()

    def version(self) -> dict:
        try:
            rows = self._run("CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition", read=True)
            r = next((r for r in rows if r["name"] == "Neo4j Kernel"), rows[0])
            return {"neo4j": r["versions"][0], "edition": r["edition"]}
        except Exception:  # noqa: BLE001  (informative)
            return {}
