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

from . import Edge, GraphBackend, Node, Path, Unscopable

PARTITION = "mimirsynth_partition"  # the parameter the scoped Cypher reads the partition from
BATCH = 1000

# --- scoping the Cypher written for one graph per brain ---------------------------------------------------------------------
#
# `scope()` reads the Cypher as Neo4j does (strings, backtick names, comments, the clause each part is in) and adds the partition to
# every node pattern. A node pattern is a parenthesis in a pattern position: anywhere at the top of a MATCH, MERGE or CREATE clause
# (after the clause, a comma, a path name's `=`, a path selector such as `ANY` or `SHORTEST 2`, a quantifier), next to a relationship
# (`-`, `->`, `<-`) or at the start of an `EXISTS` / `COUNT` / `COLLECT` subquery. A parenthesis in a pattern position whose inside it
# cannot read as a node (a label expression with `%`, `IS` or parentheses, a dynamic label, a comment) is refused: it is never let
# through unscoped. The maps and inline `WHERE` of a node are scoped too, since a value can hold a subquery of its own.
#
# The read-only console runs Cypher that people write, so it asks for more (`strict`, and `check_console()`): it also refuses
# variable-length relationships and quantified paths, whose intermediate nodes no node pattern names, and everything the lexer
# cannot be sure Neo4j reads the same way (comments, parameters, characters outside ASCII, `\u` escapes, which Neo4j decodes before
# it reads the query), and any function outside an allow-list of Neo4j's own (no plugin function runs: APOC's run Cypher from a string).

_IDENT = r"(?:`(?:[^`]|``)*`|[^\W\d]\w*)"
_NODE = re.compile(rf"^\s*(?P<var>{_IDENT})?\s*(?P<labels>(?::\s*!?\s*{_IDENT}\s*(?:[|&]\s*!?\s*{_IDENT}\s*)*)*)(?P<rest>.*)$", re.S)
_WORD = re.compile(r"[^\W\d]\w*")
_PARAM = re.compile(r"\$\w*")
_CLAUSES = {"MATCH", "MERGE", "CREATE", "WHERE", "RETURN", "WITH", "SET", "DELETE", "DETACH", "REMOVE", "UNWIND", "ORDER", "LIMIT",
            "SKIP", "CALL", "UNION", "FOREACH", "YIELD", "ON", "USING"}
_PATTERNS = {"MATCH", "MERGE", "CREATE"}  # the clauses whose top level is patterns
_WRITES = {"CREATE", "MERGE"}
_SELECTORS = {"MATCH", "MERGE", "CREATE", "ANY", "ALL", "SHORTEST", "PATH", "PATHS", "GROUPS"}  # words a pattern can follow there
_SUBQUERIES = {"EXISTS", "COUNT", "COLLECT"}
_PATH_CALLS = {"SHORTESTPATH", "ALLSHORTESTPATHS"}
_LINE_END = "\n\r\x0b\x0c\x1c\x1d\x1e\x85  "  # Neo4j ends a `//` comment at \v and \f as well: ending it early is safe
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


def _comment_end(q: str, i: int) -> int:
    """The index after the comment that starts at `i` (`//` or `/*`)."""
    if q.startswith("//", i):
        j = i + 2
        while j < len(q) and q[j] not in _LINE_END:
            j += 1
        return j
    j = q.find("*/", i + 2)
    return len(q) if j < 0 else j + 2


def _matching(q: str, i: int, open_: str, close: str) -> int:
    """The index of the bracket that closes the one at `i`, or -1."""
    depth, j = 0, i
    while j < len(q):
        c = q[j]
        if c in "'\"`":
            j = _skip_quoted(q, j)
            continue
        if q.startswith("//", j) or q.startswith("/*", j):
            j = _comment_end(q, j)
            continue
        if c == open_:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _node(inner: str) -> tuple[str, str, str, str] | None:
    """(head, labels, map, where) when `inner` reads as the inside of a node pattern: `n:Label {k: v} WHERE n.x > 1`."""
    m = _NODE.match(inner)
    if not m:
        return None
    head, labels, rest = inner[:m.end("labels")], m["labels"] or "", m["rest"].strip()
    props = where = ""
    if rest.startswith("{"):
        end = _matching(rest, 0, "{", "}")
        if end < 0:
            return None
        props, rest = rest[:end + 1], rest[end + 1:].strip()
    if rest:
        if not re.match(r"WHERE\b", rest, re.I):
            return None
        where = rest[5:]
    return head, labels, props, where


def _scoped_node(node: tuple[str, str, str, str], strict: bool) -> str:
    head, _, props, where = node
    key = f"group_id: ${PARTITION}"
    # The key goes last: a key repeated in a map keeps its last value, so a `group_id` of the query's own cannot leave the partition.
    body = scope(props[1:-1], strict).strip() if props else ""
    out = head.rstrip() + (" " if head.strip() else "") + "{" + (body + ", " if body else "") + key + "}"
    return out + (" WHERE" + scope(where, strict, "WHERE") if where else "")


def _next_sig(q: str, i: int) -> str:
    while i < len(q):
        if q[i].isspace():
            i += 1
        elif q.startswith("//", i) or q.startswith("/*", i):
            i = _comment_end(q, i)
        else:
            break
    return q[i:i + 2]


def _arrow_end(sig: list) -> bool:
    """The last thing read ends a relationship (`-`, `->`): a `+`, `*` or `{` after it quantifies it."""
    prev, prev2 = (sig[-1] if sig else None), (sig[-2] if len(sig) > 1 else None)
    return prev == "-" and prev2 in (")", "]", "-", "<") or prev == ">" and prev2 == "-"


@dataclass
class _Frame:
    kind: str            # «top», «brace», «bracket» or «paren»
    clause: str | None   # the clause being read in it
    rel: bool = False    # the brackets of a relationship: `-[...]-`


def _position(sig: list, f: _Frame, after: str, strict: bool) -> str:
    """What a parenthesis is: «pattern», «call» (a function's arguments) or «expr»."""
    prev = sig[-1] if sig else None
    prev2 = sig[-2] if len(sig) > 1 else None
    word = prev[1] if isinstance(prev, tuple) else None
    if f.clause in _PATTERNS and f.kind != "bracket":
        if word is None or word in _SELECTORS:
            return "pattern"
        if word in _PATH_CALLS:
            return "call"
        if strict:
            raise Unscopable("pattern", word)
        return "call"  # a hint's `:Label(prop)`
    if prev == "{" or prev == "-" and prev2 in ("]", "-", ")", "<") or prev == ">" and prev2 == "-":
        return "pattern"
    if after[:1] == "-" and after[1:2] in ("[", "-", ">") or after == "<-":
        return "pattern"
    return "call" if word else "expr"


def scope(q: str, strict: bool = False, clause: str | None = None) -> str:
    """The Cypher `q`, with its node patterns scoped to the partition in `$mimirsynth_partition` (see above). Raises `Unscopable`
    when a pattern cannot be scoped, and with `strict` (the console) when a query has what the console refuses."""
    out, sig, frames, i, n = [], [], [_Frame("top", clause)], 0, len(q)
    while i < n:
        c, f = q[i], frames[-1]
        if c in "'\"`":
            j = _skip_quoted(q, i)
            lit = q[i:j]
            out.append(f"datetime({lit})" if c != "`" and _ISO.match(lit[1:-1]) else lit)  # as a parameter would go in
            sig.append("lit")
            i = j
            continue
        if q.startswith("//", i) or q.startswith("/*", i):
            j = _comment_end(q, i)
            out.append(q[i:j])
            i = j
            continue
        if c.isalpha() or c == "_":
            word = _WORD.match(q, i).group(0)
            if word.upper() in _CLAUSES and sig[-1:] != ["."]:  # not a property: `n.order`
                f.clause = word.upper()
            out.append(word)
            sig.append(("w", word.upper()))
            i += len(word)
            continue
        if c == "$":
            m = _PARAM.match(q, i)
            out.append(m.group(0))
            sig.append("lit")
            i = m.end()
            continue
        if c == "(":
            close = _matching(q, i, "(", ")")
            if _position(sig, f, _next_sig(q, close + 1) if close > 0 else "", strict) == "pattern":
                inner = q[i + 1:close] if close > 0 else q[i + 1:]
                if inner.lstrip().startswith("("):  # a parenthesized path: a quantified group, `((a)-->(b)){1,3}`
                    if strict:
                        raise Unscopable("varlength", inner.strip()[:80])
                    frames.append(_Frame("paren", f.clause if f.clause in _PATTERNS else "MATCH"))
                    out.append(c)
                    sig.append(c)
                    i += 1
                    continue
                node = _node(inner) if close > 0 else None
                if node is None:
                    raise Unscopable("pattern", inner.strip()[:80])
                bound = f.clause in _WRITES and not node[1] and not node[2] and not node[3]  # a node the query already holds
                out.append("(" + (inner if bound else _scoped_node(node, strict)) + ")")
                sig.append(")")
                i = close + 1
                continue
            word = sig[-1][1] if sig and isinstance(sig[-1], tuple) else None
            frames.append(_Frame("paren", f.clause if word is None or word in _PATH_CALLS else None))
        elif c == ")":
            if f.kind == "paren" and len(frames) > 1:
                frames.pop()
        elif c == "{":
            if strict and _arrow_end(sig):
                raise Unscopable("varlength", q[i:i + 20])
            sub = sig[-1:] and isinstance(sig[-1], tuple) and sig[-1][1] in _SUBQUERIES
            frames.append(_Frame("brace", "MATCH" if sub else None))
        elif c == "}":
            if f.kind == "brace" and len(frames) > 1:
                frames.pop()
        elif c == "[":
            frames.append(_Frame("bracket", None, rel=sig[-1:] == ["-"]))
        elif c == "]":
            if f.kind == "bracket" and len(frames) > 1:
                frames.pop()
        elif c in "+*" and strict and (_arrow_end(sig) or c == "*" and f.rel):
            raise Unscopable("varlength", q[max(0, i - 10):i + 10])
        out.append(c)
        if not c.isspace():
            sig.append(c)
        i += 1
    return "".join(out)


# --- what the console accepts on Neo4j -------------------------------------------------------------------------------------

# Neo4j's own functions (SHOW FUNCTIONS on 5.26) but `graph.*` (another database's graph) and LOAD CSV's `file()` / `linenumber()`.
CONSOLE_FUNCTIONS = frozenset("""
avg collect count max min percentilecont percentiledisc stdev stdevp sum
keys labels nodes range reduce relationships tail tobooleanlist tofloatlist tointegerlist tostringlist
e exp log log10 sqrt abs ceil floor isnan rand round sign
all any exists isempty none single
char_length character_length coalesce elementid endnode head id last length nullif properties randomuuid size startnode timestamp
toboolean tobooleanornull tofloat tofloatornull tointeger tointegerornull type valuetype
point point.distance point.withinbbox
btrim left lower ltrim normalize replace reverse right rtrim split substring tolower tostring tostringornull toupper trim upper
date datetime localdatetime localtime time duration
date.realtime date.statement date.transaction date.truncate datetime.fromepoch datetime.fromepochmillis datetime.realtime
datetime.statement datetime.transaction datetime.truncate duration.between duration.indays duration.inmonths duration.inseconds
localdatetime.realtime localdatetime.statement localdatetime.transaction localdatetime.truncate localtime.realtime
localtime.statement localtime.transaction localtime.truncate time.realtime time.statement time.transaction time.truncate
acos asin atan atan2 cos cot degrees haversin pi radians sin tan
vector.similarity.cosine vector.similarity.euclidean
""".split())
# The words a parenthesis can follow without being a function: clauses, operators, subqueries, path selectors and functions.
_CONSOLE_KEYWORDS = frozenset("""
MATCH OPTIONAL WHERE AND OR XOR NOT IN IS RETURN WITH DISTINCT UNWIND BY SKIP LIMIT OFFSET CASE WHEN THEN ELSE UNION ALL ANY NONE
SINGLE EXISTS COUNT COLLECT CONTAINS STARTS ENDS SHORTEST PATH PATHS GROUPS SHORTESTPATH ALLSHORTESTPATHS REDUCE
""".split())
_CONSOLE_CALLS = frozenset({"CALL", "SHOW", "USE", "LOAD", "TERMINATE"})   # what runs outside the query: procedures, other databases
_CONSOLE_WRITES = frozenset("""
CREATE MERGE DELETE DETACH NODETACH SET REMOVE DROP INSERT FOREACH ALTER GRANT DENY REVOKE RENAME START STOP ENABLE DEALLOCATE
REALLOCATE DRYRUN
""".split())


def _console_tokens(q: str) -> list[tuple[str, str]]:
    """The console's query as («w» word, «n» backtick name, «s» string, «p» punctuation) tokens, refusing what Neo4j could read
    otherwise than this lexer: comments, parameters, characters outside printable ASCII, backslashes and `\\u` escapes."""
    toks, i, n = [], 0, len(q)
    while i < n:
        c = q[i]
        if c in "'\"`":
            j = _skip_quoted(q, i)
            if j > n or q[j - 1] != c or j - i < 2:
                raise Unscopable("char", q[i:i + 20])  # an unterminated string or name
            body = q[i + 1:j - 1]
            if c == "`":
                if "`" in body or "\\" in body or not all(" " <= x <= "~" for x in body):
                    raise Unscopable("char", q[i:j])
                toks.append(("n", body))
            else:
                if re.search(r"\\u", body, re.I):  # Neo4j decodes \uXXXX before it reads the query: ' would end the string
                    raise Unscopable("char", "\\u")
                toks.append(("s", body))
            i = j
            continue
        if q.startswith("//", i) or q.startswith("/*", i):
            raise Unscopable("comment", q[i:i + 20])
        if c in " \t\r\n":
            i += 1
            continue
        if c == "$":
            raise Unscopable("param", q[i:i + 20])
        if not " " <= c <= "~" or c == "\\":
            raise Unscopable("char", repr(c))
        if c.isalpha() or c == "_":
            word = _WORD.match(q, i).group(0)
            toks.append(("w", word))
            i += len(word)
            continue
        toks.append(("p", c))
        i += 1
    return toks


def check_console(q: str) -> None:
    """Raises `Unscopable` when the console must not run `q` on Neo4j (see above); what it lets through, `scope()` scopes."""
    toks = _console_tokens(q)
    for k, (kind, text) in enumerate(toks):
        if kind not in ("w", "n") or k and toks[k - 1] == ("p", "."):
            continue
        if kind == "w" and text.upper() in _CONSOLE_CALLS:
            raise Unscopable("call", text)
        if kind == "w" and text.upper() in _CONSOLE_WRITES:
            raise Unscopable("write", text)
        parts, j = [toks[k]], k + 1
        while j + 1 < len(toks) and toks[j] == ("p", ".") and toks[j + 1][0] in ("w", "n"):
            parts.append(toks[j + 1])
            j += 2
        if j < len(toks) and toks[j] == ("p", "("):  # a call: `name(`, `ns.name(`, `` `ns`.name( ``
            name = ".".join(t for _, t in parts)
            plain = len(parts) == 1 and kind == "w"
            if any(p[0] == "n" for p in parts) or not (name.lower() in CONSOLE_FUNCTIONS or plain and name.upper() in _CONSOLE_KEYWORDS):
                raise Unscopable("function", name)
    scope(q, strict=True)


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

    def check_console(self, q: str) -> None:
        check_console(q)

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
