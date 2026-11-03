"""Clean the aliases of entities that only repeat their own name (#194).

Earlier merges wrote the name of a duplicate called the same as the keeper (or the same apart from case or spacing) as an alias of
itself, and the same alias could be written several times. The entity page already hides them; this removes them from the graph and
keeps every other alias as it was, in its first spelling. Undoing an old merge still works: it removes the absorbed name from the
aliases, which is a no-op when the cleanup already did.

  python -m mimirsynth.entity_aliases                 lists what would change in every brain
  python -m mimirsynth.entity_aliases --brain slug    only that brain
  python -m mimirsynth.entity_aliases --apply         writes the change
"""
import argparse
import sys

from sqlalchemy import select

from .db import graph, rows
from .entity_types import other_names


def clean(graph_name: str, apply: bool = False) -> list[dict]:
    """The entities whose aliases change, with what is removed; with `apply`, the graph is updated."""
    g = graph(graph_name)
    out = []
    for e in rows(g.query("MATCH (n:Entity) WHERE size(coalesce(n.aliases, [])) > 0 RETURN n.uuid AS uuid, n.name AS name, n.aliases AS aliases")):
        keep = other_names(e["name"], e["aliases"])
        if keep != list(e["aliases"]):
            out.append({"uuid": e["uuid"], "name": e["name"], "removed": len(e["aliases"]) - len(keep), "aliases": keep})
            if apply:
                g.query("MATCH (n:Entity {uuid:$u}) SET n.aliases = $a", {"u": e["uuid"], "a": keep})
    return out


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
