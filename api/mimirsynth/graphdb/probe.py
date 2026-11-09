"""The steps of a connection test that talk to the driver (#358): sign in, read the version, write a probe node and list what the database
holds. `graphconn.probe` runs them in order and words the result; this module only says what happened (`Unsupported`, `cause`).

Each probe opens its own short-lived connection with timeouts, never the instance's backend, so a test cannot disturb what is running.
"""
from __future__ import annotations

import secrets

from . import DEFAULT_PORTS, Connection

PROBE_PREFIX = "_mimirsynth_probe_"  # hidden («_» first) like the snapshots: never listed, never a brain
MIN_NEO4J = (5, 26)  # dynamic labels and types, CALL (n) {…} IN TRANSACTIONS
MIN_FALKOR = 40000  # the graph module's version as FalkorDB reports it (major·10000 + minor·100 + patch): 4.0 brought the vectors


class Unsupported(Exception):
    """The server answers but cannot hold the brains: `what` is `redis` (no graph module), `falkordb` or `neo4j` (too old)."""

    def __init__(self, what: str, version: str | None = None):
        super().__init__(f"{what} {version or ''}".strip())
        self.what, self.version = what, version


def falkor_version(v: int) -> str:
    return f"{v // 10000}.{v // 100 % 100}.{v % 100}"


class FalkorProbe:
    def __init__(self, conn: Connection, timeout: float):
        from falkordb import FalkorDB
        self.client = FalkorDB(host=conn.host, port=conn.port or DEFAULT_PORTS["falkordb"], username=conn.user or None,
                               password=conn.password or None, ssl=conn.tls, socket_timeout=timeout, socket_connect_timeout=timeout)

    def auth(self) -> None:
        self.client.connection.ping()

    def version(self) -> dict:
        from redis.exceptions import NoPermissionError
        try:
            modules = self.client.connection.execute_command("MODULE", "LIST")
        except NoPermissionError:  # an ACL user without MODULE: the vector in the write step still shows it is FalkorDB
            return {"server": "FalkorDB", "version": None}
        graph = None
        for m in modules:
            d = dict(zip(*[iter(x.decode() if isinstance(x, bytes) else x for x in m)] * 2))
            if d.get("name") == "graph":
                graph = int(d.get("ver") or 0)
        if graph is None:
            raise Unsupported("redis")
        if graph < MIN_FALKOR:
            raise Unsupported("falkordb", falkor_version(graph))
        return {"server": "FalkorDB", "version": falkor_version(graph)}

    def write(self) -> None:
        g = self.client.select_graph(PROBE_PREFIX + secrets.token_hex(4))
        try:
            g.query("CREATE (:MimirSynthProbe {v: vecf32([1.0, 0.0])})")  # vecf32: what the brains' vectors need
        finally:
            try:
                g.delete()
            except Exception:  # noqa: BLE001  (nothing was created, or it is already gone)
                pass

    def graphs(self, limit: int) -> list[dict]:
        names = sorted(n for n in self.client.list_graphs() if not n.startswith("_"))
        return [{"name": n, "nodes": int(self.client.select_graph(n).ro_query("MATCH (n) RETURN count(n)").result_set[0][0])}
                for n in names[:limit]]

    def close(self) -> None:
        self.client.connection.close()


class Neo4jProbe:
    def __init__(self, conn: Connection, timeout: float):
        from neo4j import GraphDatabase
        self.timeout, self.database = timeout, conn.database or None
        self.driver = GraphDatabase.driver(conn.neo4j_uri(), auth=(conn.user or "neo4j", conn.password), connection_timeout=timeout,
                                           connection_acquisition_timeout=timeout, max_transaction_retry_time=0,
                                           notifications_min_severity="OFF")

    def _q(self, q: str, params: dict | None = None, write: bool = False) -> list:
        from neo4j import READ_ACCESS, WRITE_ACCESS, Query
        with self.driver.session(database=self.database, default_access_mode=WRITE_ACCESS if write else READ_ACCESS) as s:
            return list(s.run(Query(q, timeout=self.timeout), params or {}))

    def auth(self) -> None:
        self.driver.verify_connectivity()
        if not self.database:  # Graphiti's driver needs the database by name, as the backend does
            self.database = self._q("CALL db.info() YIELD name RETURN name")[0]["name"]
        else:
            self._q("RETURN 1 AS ok")

    def version(self) -> dict:
        rows = self._q("CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition")
        r = next((r for r in rows if r["name"] == "Neo4j Kernel"), rows[0])
        v = str(r["versions"][0])
        try:
            parts = tuple(int(p) for p in v.split("-")[0].split(".")[:2])
        except ValueError:
            parts = MIN_NEO4J  # a version this does not understand is let through: the write step still has to pass
        if parts < MIN_NEO4J:
            raise Unsupported("neo4j", v)
        return {"server": "Neo4j", "version": v, "edition": r["edition"], "database": self.database}

    def write(self) -> None:
        self._q("CREATE (n:MimirSynthProbe {group_id: $g}) DELETE n", {"g": PROBE_PREFIX + secrets.token_hex(4)}, write=True)

    def graphs(self, limit: int) -> list[dict]:
        rows = self._q("MATCH (n) WHERE n.group_id IS NOT NULL WITH n.group_id AS g, count(*) AS c "
                       "WHERE g IS :: STRING AND NOT g STARTS WITH '_' RETURN g, c ORDER BY g LIMIT $m", {"m": limit})
        return [{"name": r["g"], "nodes": int(r["c"])} for r in rows]

    def close(self) -> None:
        self.driver.close()


def opener(conn: Connection, timeout: float) -> FalkorProbe | Neo4jProbe:
    return (Neo4jProbe if conn.backend == "neo4j" else FalkorProbe)(conn, timeout)


def cause(e: Exception) -> str | None:
    """What a driver's error means for a connection test: auth, permission, database, timeout, protocol (it answers, but not as that
    backend, or not without TLS), redis (no graph module), or None when it is something else."""
    from neo4j.exceptions import AuthError, ClientError, Forbidden, ServiceUnavailable
    from redis.exceptions import AuthenticationError, NoPermissionError, ResponseError
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeout
    text = str(e)
    if isinstance(e, (AuthError, AuthenticationError)) or (isinstance(e, ResponseError) and text.startswith(("WRONGPASS", "NOAUTH"))):
        return "auth"
    if isinstance(e, (Forbidden, NoPermissionError)) or (isinstance(e, ClientError) and "Security" in (e.code or "")):
        return "permission"
    if isinstance(e, ClientError) and (e.code or "").endswith("DatabaseNotFound"):
        return "database"
    if isinstance(e, (RedisTimeout, TimeoutError)):
        return "timeout"
    if isinstance(e, (ServiceUnavailable, RedisConnectionError)):
        return "protocol"
    if isinstance(e, ResponseError) and "unknown command" in text.lower():
        return "redis"
    return None
