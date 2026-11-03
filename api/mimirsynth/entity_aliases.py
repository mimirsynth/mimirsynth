"""Clean the aliases of entities that only repeat their own name (#194, #202).

Earlier merges wrote the name of a duplicate called the same as the keeper (or the same apart from case or spacing) as an alias of
itself, and the same alias could be written several times. The entity page already hides them; this removes them from the graph and
keeps every other alias as it was, in its first spelling.

From Content quality (brain administrators): a preview that writes nothing, and «Apply», a background job that first takes a copy of
the graph and records the change in the vocabulary history with every entity's aliases before and after, so Recent changes can undo
it. Undoing restores an entity's aliases only when they are still the ones the cleanup left; an entity that changed since is skipped.
Undoing an old merge still works: it removes the absorbed name from the aliases, a no-op when the cleanup already did.

The command does the same without the history:

  python -m mimirsynth.entity_aliases                 lists what would change in every brain
  python -m mimirsynth.entity_aliases --brain slug    only that brain
  python -m mimirsynth.entity_aliases --apply         writes the change
"""
import argparse
import sys

from fastapi import APIRouter, Depends
from sqlalchemy import select

from . import jobs
from .db import graph, rows
from .deps import BrainCtx, admin_of_brain, audit
from .entity_types import other_names, snapshot_graph

router = APIRouter(prefix="/api/brains/{slug}/vocab/entity-aliases")


def plan(graph_name: str) -> list[dict]:
    """The entities whose aliases would change: what they have, what stays (`aliases`) and what goes (`dropped`, and how many)."""
    out = []
    for e in rows(graph(graph_name).query("MATCH (n:Entity) WHERE size(coalesce(n.aliases, [])) > 0 "
                                          "RETURN n.uuid AS uuid, n.name AS name, n.aliases AS aliases ORDER BY n.name")):
        before = list(e["aliases"])
        keep = other_names(e["name"], before)
        if keep != before:
            rest, dropped = list(keep), []
            for a in before:  # each kept alias consumes its first occurrence; every other occurrence goes
                if a in rest:
                    rest.remove(a)
                else:
                    dropped.append(a)
            out.append({"uuid": e["uuid"], "name": e["name"], "removed": len(before) - len(keep), "aliases": keep, "before": before, "dropped": dropped})
    return out


def clean(graph_name: str, apply: bool = False) -> list[dict]:
    """The entities whose aliases change, with what is removed; with `apply`, the graph is updated."""
    changed = plan(graph_name)
    if apply:
        g = graph(graph_name)
        for c in changed:
            g.query("MATCH (n:Entity {uuid:$u}) SET n.aliases = $a", {"u": c["uuid"], "a": c["aliases"]})
    return changed


def undo(graph_name: str, detail: dict) -> int:
    """Puts back the aliases the cleanup removed, entity by entity, only where they are still what it left. Returns how many."""
    g = graph(graph_name)
    restored = 0
    for e in detail.get("entries", []):
        cur = rows(g.query("MATCH (n:Entity {uuid:$u}) RETURN coalesce(n.aliases, []) AS a", {"u": e["uuid"]}))
        if cur and list(cur[0]["a"]) == e["after"]:
            g.query("MATCH (n:Entity {uuid:$u}) SET n.aliases = $a", {"u": e["uuid"], "a": e["before"]})
            restored += 1
    return restored


@router.get("")
def preview(ctx: BrainCtx = Depends(admin_of_brain)):
    items = plan(ctx.brain.graph_name)
    return {"entities": len(items), "aliases": sum(i["removed"] for i in items),
            "items": [{k: i[k] for k in ("uuid", "name", "aliases", "dropped")} for i in items]}


@router.post("", status_code=202)
def apply(ctx: BrainCtx = Depends(admin_of_brain)):
    if not plan(ctx.brain.graph_name):
        return {"job": None, "entities": 0}  # nothing to clean: nothing is written, not even the copy
    job = jobs.submit("vocab.entity_aliases", ctx.brain.id, {"graph": ctx.brain.graph_name, "user_id": ctx.user.id},
                      "Limpiar alias repetidos", ctx.user.id, dedupe_key=f"vocab.entity_aliases:{ctx.brain.id}")
    return {"job": job}


@jobs.register("vocab.entity_aliases", "Limpiar alias repetidos", limit=1)
def _job_clean(ctx: "jobs.JobCtx", p: dict) -> dict:
    from .models import Brain, User, VocabOp
    from .store import _factory
    changed = plan(p["graph"])
    if not changed:
        return {"entities": 0, "aliases": 0}
    ctx.progress(0, len(changed), "copia del grafo")
    snap = snapshot_graph(p["graph"], "alias")
    g = graph(p["graph"])
    entries = []
    for i, c in enumerate(changed, 1):
        ctx.check()
        g.query("MATCH (n:Entity {uuid:$u}) SET n.aliases = $a", {"u": c["uuid"], "a": c["aliases"]})
        entries.append({"uuid": c["uuid"], "name": c["name"], "before": c["before"], "after": c["aliases"]})
        ctx.progress(i, len(changed), c["name"][:100])
    n = sum(c["removed"] for c in changed)
    with _factory()() as db:
        brain, user = db.get(Brain, ctx.brain_id), db.get(User, p.get("user_id")) if p.get("user_id") else None
        summary = f"Limpiados {n} alias repetidos en {len(entries)} entidades"
        db.add(VocabOp(brain_id=ctx.brain_id, kind="entity.aliases", summary=summary, detail={"entries": entries, "snapshot": snap}, user_id=user.id if user else None))
        db.commit()
        audit(db, user, "vocab.entity.aliases", brain, aliases=n, entities=len(entries), snapshot=snap)
    return {"entities": len(entries), "aliases": n, "snapshot": snap}


def main(argv: list[str] | None = None) -> int:
    from .models import Brain
    from .store import _factory
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--brain", help="only this brain (its slug)")
    ap.add_argument("--apply", action="store_true", help="write the change; without it, only list it")
    a = ap.parse_args(argv)
    with _factory()() as db:
        q = select(Brain).order_by(Brain.slug)
        brains = db.scalars(q.where(Brain.slug == a.brain) if a.brain else q).all()
    if a.brain and not brains:
        print(f"no brain with the slug {a.brain}")
        return 1
    for b in brains:
        changed = clean(b.graph_name, a.apply)
        n = sum(c["removed"] for c in changed)
        print(f"{b.slug}: {n} aliases equal to the name in {len(changed)} entities{' removed' if a.apply else ''}")
        for c in changed[:20]:
            print(f"  - {c['name']}: {c['removed']}")
    if not a.apply:
        print("Nothing written. Run again with --apply to remove them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
