"""FalkorDB: one graph per brain, on a Redis server with the graph module."""
from __future__ import annotations

from functools import cached_property
from typing import Any

from . import Edge, GraphBackend, Node, Path


class FalkorBackend(GraphBackend):
    name = "falkordb"
    label = "FalkorDB"

    def __init__(self, host: str, port: int, username: str | None = None, password: str | None = None, tls: bool = False):
        self.host, self.port, self.username, self.password, self.tls = host, port, username, password, tls

    @cached_property
    def client(self):
        from falkordb import FalkorDB
        return FalkorDB(host=self.host, port=self.port, username=self.username, password=self.password, ssl=self.tls)

    def graph(self, name: str):
        return self.client.select_graph(name)

    def list_graphs(self) -> list[str]:
        return list(self.client.list_graphs())

    def copy_graph(self, src: str, dst: str) -> None:
        self.client.select_graph(src).copy(dst)

    def delete_graph(self, name: str) -> None:
        self.client.select_graph(name).delete()

    def graphiti_driver(self, name: str):
        from graphiti_core.driver.falkordb_driver import FalkorDriver
        if self.tls:  # Graphiti's driver has no TLS switch of its own: it takes a client made with one
            from falkordb.asyncio import FalkorDB as AsyncFalkorDB
            return FalkorDriver(falkor_db=AsyncFalkorDB(host=self.host, port=self.port, username=self.username, password=self.password, ssl=True),
                                database=name)
        return FalkorDriver(host=self.host, port=self.port, username=self.username, password=self.password, database=name)

    def vector(self, expr: str) -> str:
        return f"vecf32({expr})"

    def cosine(self, a: str, b: str) -> str:
        return f"(2 - vec.cosineDistance({a}, {b}))/2"  # cosineDistance is 1 - cos

    def value(self, v: Any) -> Any:
        from falkordb.edge import Edge as FEdge
        from falkordb.node import Node as FNode
        from falkordb.path import Path as FPath
        if isinstance(v, FNode):
            return Node(str(v.id), v.labels, v.properties)
        if isinstance(v, FEdge):
            return Edge(str(v.id), v.relation, str(v.src_node), str(v.dest_node), v.properties)
        if isinstance(v, FPath):
            return Path([self.value(n) for n in v.nodes()], [self.value(e) for e in v.edges()])
        return v

    def version(self) -> dict:
        out: dict = {}
        try:
            conn = self.client.connection
            out["redis"] = conn.info("server").get("redis_version")
            for m in conn.execute_command("MODULE", "LIST"):
                d = dict(zip(*[iter(x.decode() if isinstance(x, bytes) else x for x in m)] * 2))
                if d.get("name") == "graph":
                    out["graph_module"] = d.get("ver")
        except Exception:  # noqa: BLE001  (informative: a dump's own header is what decides)
            pass
        return out

    def memory(self) -> tuple[int, int]:
        """`maxmemory` as the limit or, without one, the system's memory."""
        info = self.client.connection.info("memory")
        return int(info.get("used_memory", 0)), int(info.get("maxmemory") or info.get("total_system_memory") or 0)

    def can_dump(self) -> bool:
        return True

    def dump(self, name: str) -> bytes:
        return self.client.connection.dump(name)

    def restore(self, name: str, payload: bytes) -> None:
        self.client.connection.restore(name, 0, payload)

    def close(self) -> None:
        if "client" in self.__dict__:
            self.client.connection.close()
