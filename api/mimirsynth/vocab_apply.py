"""Aplica el vocabulario del brain al escribir: tras ingerir un episodio, normaliza las relaciones con alias y enlaza con su
entidad principal las entidades nuevas que reaparecen con el nombre de un duplicado ya fusionado. Cierra el bucle de la limpieza:
lo que se unificó deja de reaparecer. Las fusiones automáticas quedan registradas (auto) y son reversibles como las manuales."""
import logging
from datetime import datetime, timedelta, timezone

from .db import graph, rows
from .entity_types import _merge_all
from .models import Brain, VocabOp
from .vocab import alias_map, canon_rel, resolve

log = logging.getLogger("mimirsynth.vocab_apply")


def apply(db, brain: Brain, rep: dict) -> None:
    """Consume rep['_edges'] / rep['_nodes'] (los deja add_episode) y añade el resultado al informe de ingesta."""
    edges = rep.pop("_edges", [])
    nodes = rep.pop("_nodes", [])
    try:
        g = graph(brain.graph_name)
        amap = alias_map(db, brain.id)
        n_alias = 0
        for uuid, name in edges:
            target = resolve(name, amap)
            if target != canon_rel(name):
                g.query("MATCH ()-[r:RELATES_TO {uuid:$u}]->() SET r.name = $n", {"u": uuid, "n": target})
                n_alias += 1
        merged, ambiguous = [], []
        for uuid, name, is_new in nodes:
            if not is_new or not name:
                continue
            ks = rows(g.query(
                "MATCH (k:Entity) WHERE k.uuid <> $u AND any(a IN coalesce(k.aliases, []) WHERE toLower(a) = toLower($n)) RETURN k.uuid AS uuid, k.name AS name",
                {"u": uuid, "n": name}))
            if len(ks) > 1:
                ambiguous.append(name)
            elif len(ks) == 1:
                entries: list[dict] = []
                keeper, dup = ks[0], {"uuid": uuid, "name": name}
                _merge_all(g, keeper, [dup], entries)
                db.add(VocabOp(brain_id=brain.id, kind="entity.merge", summary=f"Auto: {name} → {keeper['name']} (al ingerir)",
                               detail={"keeper": keeper, "entries": entries, "snapshot": None, "onto_before": None, "auto": True}))
                db.commit()
                merged.append(name)
        if n_alias:
            rep["aliased_edges"] = n_alias
        if merged:
            rep["auto_merged"] = merged
        if ambiguous:
            rep["merge_ambiguous"] = ambiguous
    except Exception:  # noqa: BLE001 — la ingesta ya se hizo; esto es un refinamiento
        log.exception("no se pudo aplicar el vocabulario tras ingerir")
        rep["vocab_error"] = True
