"""Verifiable facts (#293, first part): a fact may carry a **probe**, a verifier plus its parameters, that checks it against a live system
(where something runs, which address or version it has, whether it exists). Many facts describe something that can be queried, and
today they stay current until someone happens to contradict them.

- **Verifiers are plugins** with a small interface: `check(fact, params) -> Result(state, evidence, value)`, where `state` is
  `verified`, `refuted` or `unverifiable`. MimirSynth ships none that knows a given infrastructure: only the example `json_inventory`,
  which reads a JSON file of `{key: value}` the instance can read (an inventory exported by another tool).
- **Loading external code is an explicit administrator decision**: verifiers in other files are only loaded from the folder named by
  `MIMIRSYNTH_VERIFIERS_DIR` (mount it with the Docker image), each a `.py` that calls `register` on a `Verifier` subclass. Without
  the variable nothing outside this file is loaded.
- **Credentials** a verifier needs are set per brain by its administrators (`PUT /verifiers/{id}`) and stored sealed, like the wiki
  and notification secrets; they are never returned. A probe runs in a background job with those settings, never with the
  permissions of whoever reads the brain.
- **Once a day** (and «Run now»), each probe of the brain is checked. `verified` renews the fact's confirmation date (as confirming it
  by hand, so shelf life counts from it). `refuted` becomes a **proposal** that replaces the fact (a claim with `supersedes`, #295),
  with the evidence and, when the verifier gives it, the current value: a person decides it, nothing changes on its own. A fact no
  longer current is left alone.
- **In the recall**, a fact with a probe says its state and when it was checked (`verification` in the JSON, and in the context).
"""
import importlib.util
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from . import jobs
from .db import rows
from .deps import BrainCtx, admin_of_brain, audit, brain_access
from .models import Brain, FactConfirmation, FactProbe, Proposal, VerifierConfig
from .store import _factory

log = logging.getLogger("mimirsynth.verify")
router = APIRouter(prefix="/api/brains/{slug}")
curator = brain_access("curator")
KIND = "verify.run"
STATES = ("verified", "refuted", "unverifiable")
MAX_PER_RUN = 500
EVERY = timedelta(hours=24)
CACHE_SECONDS = 30.0


@dataclass
class Result:
    state: str                 # verified | refuted | unverifiable
    evidence: str = ""         # what the verifier saw, for the curator (never a secret)
    value: str | None = None   # the current value, when the verifier knows it


@dataclass
class Param:
    """A setting a verifier needs: per brain (`config`, may be secret) or per probe (`params`)."""
    name: str
    label: str
    secret: bool = False
    required: bool = True
    help: str = ""


class Verifier:
    """Contract of a verifier: read-only, no state between calls, and fast (a slow system makes the fact `unverifiable`)."""
    id = ""
    label = ""
    config: list[Param] = []   # set once per brain by its administrators
    params: list[Param] = []   # set on each probe

    def __init__(self, values: dict):
        for p in self.config:
            if p.required and not str(values.get(p.name, "")).strip():
                raise ValueError(f"falta «{p.label}»")
        self.v = {p.name: str(values.get(p.name, "")).strip() for p in self.config}

    def check(self, fact: dict, params: dict) -> Result:   # fact: {uuid, fact, name (relation), source, target, valid_at}
        raise NotImplementedError


REGISTRY: dict[str, type[Verifier]] = {}


def register(cls: type[Verifier]) -> type[Verifier]:
    REGISTRY[cls.id] = cls
    return cls


def _norm(s) -> str:
    return " ".join(str(s or "").lower().split())


@register
class JsonInventory(Verifier):
    """The example: a JSON file `{key: value}` (or `{key: [values]}`). The fact is verified if the value under the probe's key is the
    fact's target, refuted if it is another one, unverifiable if the key is not there."""
    id = "json_inventory"
    label = "Inventario JSON"
    config = [Param("path", "Ruta del fichero JSON", help="Un fichero que la instancia puede leer, por ejemplo montado en el contenedor.")]
    params = [Param("key", "Clave en el inventario", help="La entrada del inventario que dice el valor actual (por ejemplo, el nombre del servicio).")]

    def check(self, fact: dict, params: dict) -> Result:
        import json
        data = json.loads(Path(self.v["path"]).read_text(encoding="utf-8"))
        key = str(params.get("key") or "")
        if key not in data:
            return Result("unverifiable", f"«{key}» no está en el inventario")
        found = data[key] if isinstance(data[key], list) else [data[key]]
        if _norm(fact.get("target")) in {_norm(v) for v in found}:
            return Result("verified", f"el inventario dice «{key}»: {', '.join(map(str, found))}")
        return Result("refuted", f"el inventario dice «{key}»: {', '.join(map(str, found))}", str(found[0]) if len(found) == 1 else None)


def load_dir(path: str | None = None) -> list[str]:
    """Loads the verifiers of `MIMIRSYNTH_VERIFIERS_DIR` (the administrator's opt-in). Returns the ids it added."""
    folder = path or os.environ.get("MIMIRSYNTH_VERIFIERS_DIR", "")
    if not folder:
        return []
    before = set(REGISTRY)
    for f in sorted(Path(folder).glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(f"mimirsynth_verifier_{f.stem}", f)
            spec.loader.exec_module(importlib.util.module_from_spec(spec))
        except Exception:  # noqa: BLE001  (one broken file does not stop the others)
            log.exception("no se pudo cargar el verificador %s", f)
    return sorted(set(REGISTRY) - before)


# --- per-brain settings -------------------------------------------------------------------------

def _config(db, brain_id: int, vid: str) -> dict:
    from .secretbox import unseal
    row = db.scalar(select(VerifierConfig).where(VerifierConfig.brain_id == brain_id, VerifierConfig.verifier == vid))
    secret = {p.name for p in REGISTRY[vid].config if p.secret} if vid in REGISTRY else set()
    return {k: unseal(v) if k in secret else v for k, v in ((row.values if row else None) or {}).items()}


def make(db, brain_id: int, vid: str) -> Verifier:
    if vid not in REGISTRY:
        raise ValueError(f"verificador desconocido: {vid}")
    return REGISTRY[vid](_config(db, brain_id, vid))


def _describe(db, brain_id: int) -> list[dict]:
    out = []
    for cls in REGISTRY.values():
        stored = _config(db, brain_id, cls.id)
        out.append({"id": cls.id, "label": cls.label,
                    "config": [{"name": p.name, "label": p.label, "secret": p.secret, "required": p.required, "help": p.help,
                                "set": bool(stored.get(p.name)), **({} if p.secret else {"value": stored.get(p.name, "")})} for p in cls.config],
                    "params": [{"name": p.name, "label": p.label, "required": p.required, "help": p.help} for p in cls.params]})
    return out


# --- checking -----------------------------------------------------------------------------------

_FACT = ("MATCH (a:Entity)-[r:RELATES_TO {uuid:$u}]->(b:Entity) RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact, r.valid_at AS valid_at, "
         "r.invalid_at AS invalid_at, r.expired_at AS expired_at, a.name AS source, b.name AS target")


def _fact(graph, uuid: str) -> dict | None:
    hit = rows(graph.query(_FACT, {"u": uuid}))
    return hit[0] if hit else None


def check(db, graph, brain: Brain, probe: FactProbe) -> Result:
    """Runs one probe and stores its result. Never raises: an error is `unverifiable` with what went wrong."""
    f = _fact(graph, probe.fact_uuid)
    if not f or f["invalid_at"] or f["expired_at"]:
        res = Result("unverifiable", "el hecho ya no está vigente")
    else:
        try:
            res = make(db, brain.id, probe.verifier).check(f, probe.params or {})
            if res.state not in STATES:
                res = Result("unverifiable", f"el verificador devolvió un estado desconocido: {res.state}")
        except Exception as e:  # noqa: BLE001
            res = Result("unverifiable", f"error del verificador: {str(e)[:300]}")
    now = datetime.now(timezone.utc)
    probe.state, probe.evidence, probe.value, probe.checked_at = res.state, res.evidence[:1000], res.value, now
    if res.state == "verified":
        c = db.scalar(select(FactConfirmation).where(FactConfirmation.brain_id == brain.id, FactConfirmation.fact_uuid == probe.fact_uuid))
        if not c:
            c = FactConfirmation(brain_id=brain.id, fact_uuid=probe.fact_uuid)
            db.add(c)
        c.confirmed_at, c.user_id = now, probe.created_by
    elif res.state == "refuted" and f and not f["invalid_at"]:
        _propose(db, graph, brain, probe, f, res)
    db.commit()
    return res


def _propose(db, graph, brain: Brain, probe: FactProbe, f: dict, res: Result) -> None:
    """A refuted fact becomes a proposal that replaces it, unless one is already pending for it."""
    from . import claims as claims_mod
    from .curator import _pending_targets
    if probe.fact_uuid in _pending_targets(db, brain.id) or not probe.created_by:
        return
    claim = {"subject": f["source"], "relation": f["name"], "value": res.value or f["target"], "valid_from": None, "supersedes": f["uuid"]}
    checked = claims_mod.check(graph, [claim], None, set())
    body = f"Según {REGISTRY[probe.verifier].label}, {f['source']} → {res.value}." if res.value else ""
    p = Proposal(brain_id=brain.id, author_id=probe.created_by, name=f"Verificación: «{(f['fact'] or '')[:200]}» ya no es cierto"[:255],
                 body=body, source="text", status="pending", source_description=f"verifier: {probe.verifier}", category="verifier.refuted",
                 claims=checked, related_verdict="new", decision={"verifier": {"id": probe.verifier, "evidence": res.evidence, "value": res.value}})
    db.add(p)
    db.flush()
    audit(db, None, "proposal.submit", brain, id=p.id, status="pending", by="verifier", fact=f["uuid"])


@jobs.register(KIND, "Verificar hechos", limit=1)
def _job(ctx: "jobs.JobCtx", p: dict) -> dict:
    from .db import graph
    counts = dict.fromkeys(STATES, 0)
    with _factory()() as db:
        b = db.get(Brain, ctx.brain_id)
        g = graph(b.graph_name)
        probes = list(db.scalars(select(FactProbe).where(FactProbe.brain_id == b.id).order_by(FactProbe.checked_at.is_not(None), FactProbe.checked_at)
                                 .limit(MAX_PER_RUN)))
        for n, pr in enumerate(probes):
            ctx.check()
            ctx.progress(n, len(probes))
            counts[check(db, g, b, pr).state] += 1
    forget(ctx.brain_id)
    return counts


def submit(brain_id: int, user_id: int | None = None) -> int:
    return jobs.submit(KIND, brain_id, {}, "Verificar hechos", user_id, dedupe_key=f"{KIND}:{brain_id}")


def due(now: datetime | None = None) -> list[int]:
    """The brains with a probe not checked in the last day: one job each. Called every few minutes."""
    now = now or datetime.now(timezone.utc)
    with _factory()() as db:
        ids = list(db.scalars(select(FactProbe.brain_id).where((FactProbe.checked_at.is_(None)) | (FactProbe.checked_at < now - EVERY)).distinct()))
    return [submit(b) for b in ids]


# --- the recall -------------------------------------------------------------------------------

_CACHE: dict[int, tuple[float, bool]] = {}
_LOCK = threading.Lock()


def forget(brain_id: int) -> None:
    with _LOCK:
        _CACHE.pop(brain_id, None)


def _has_probes(brain_id: int) -> bool:
    hit = _CACHE.get(brain_id)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    with _factory()() as db:
        has = bool(db.scalar(select(func.count()).select_from(FactProbe).where(FactProbe.brain_id == brain_id)))
    with _LOCK:
        _CACHE[brain_id] = (time.monotonic(), has)
    return has


def mark(brain_id: int, facts: list[dict]) -> list[dict]:
    """Adds `verification` {state, checked_at, verifier} to the recall's own facts that have a probe. Free for a brain without probes."""
    if not _has_probes(brain_id):
        return facts
    own = {f["uuid"]: f for f in facts if not f.get("origin") and f.get("uuid")}
    if not own:
        return facts
    with _factory()() as db:
        for pr in db.scalars(select(FactProbe).where(FactProbe.brain_id == brain_id, FactProbe.fact_uuid.in_(list(own)))):
            own[pr.fact_uuid]["verification"] = {"state": pr.state or "pending", "checked_at": pr.checked_at.isoformat() if pr.checked_at else None,
                                                 "verifier": pr.verifier}
    return facts


# --- API --------------------------------------------------------------------------------------

class ConfigIn(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class ProbeIn(BaseModel):
    verifier: str = Field(min_length=1, max_length=64)
    params: dict[str, str] = Field(default_factory=dict)


def _probe_out(pr: FactProbe) -> dict:
    return {"fact_uuid": pr.fact_uuid, "verifier": pr.verifier, "params": pr.params or {}, "state": pr.state, "evidence": pr.evidence,
            "value": pr.value, "checked_at": pr.checked_at, "created_at": pr.created_at}


@router.get("/verifiers")
def list_verifiers(ctx: BrainCtx = Depends(curator)):
    """The verifiers this instance has (the example and those of MIMIRSYNTH_VERIFIERS_DIR) and what this brain set for each."""
    return {"items": _describe(ctx.db, ctx.brain.id)}


@router.put("/verifiers/{vid}")
def set_verifier(vid: str, body: ConfigIn, ctx: BrainCtx = Depends(admin_of_brain)):
    """A verifier's settings for this brain. A secret left empty keeps the stored one; secrets are sealed and never returned."""
    from .secretbox import seal
    if vid not in REGISTRY:
        raise HTTPException(404, "verificador desconocido")
    cls = REGISTRY[vid]
    old = _config(ctx.db, ctx.brain.id, vid)
    values = {}
    for p in cls.config:
        v = str(body.values.get(p.name, "")).strip()
        if p.secret:
            v = v or old.get(p.name, "")
            values[p.name] = seal(v) if v else ""
        else:
            values[p.name] = v
    row = ctx.db.scalar(select(VerifierConfig).where(VerifierConfig.brain_id == ctx.brain.id, VerifierConfig.verifier == vid))
    if not row:
        row = VerifierConfig(brain_id=ctx.brain.id, verifier=vid)
        ctx.db.add(row)
    row.values = values
    ctx.db.commit()
    audit(ctx.db, ctx.user, "verifier.settings", ctx.brain, verifier=vid, fields=sorted(values))
    return {"items": _describe(ctx.db, ctx.brain.id)}


@router.get("/probes")
def list_probes(ctx: BrainCtx = Depends(curator)):
    probes = list(ctx.db.scalars(select(FactProbe).where(FactProbe.brain_id == ctx.brain.id).order_by(FactProbe.id.desc()).limit(1000)))
    facts = {}   # what each probe checks, to read it: the fact's text and its entity
    if probes:
        for r in rows(ctx.graph.query("MATCH (a:Entity)-[r:RELATES_TO]->(:Entity) WHERE r.uuid IN $u RETURN r.uuid AS uuid, r.fact AS fact, "
                                      "a.name AS source, a.uuid AS source_uuid, r.invalid_at AS invalid_at", {"u": [p.fact_uuid for p in probes]})):
            facts[r["uuid"]] = r
    return {"items": [{**_probe_out(p), **{k: (facts.get(p.fact_uuid) or {}).get(k) for k in ("fact", "source", "source_uuid", "invalid_at")}}
                      for p in probes]}


@router.put("/facts/{uuid}/probe")
def set_probe(uuid: str, body: ProbeIn, ctx: BrainCtx = Depends(curator)):
    """Attaches a probe to a current fact of this brain (or replaces it). It is checked on the next run."""
    if body.verifier not in REGISTRY:
        raise HTTPException(422, "verificador desconocido")
    missing = [p.label for p in REGISTRY[body.verifier].params if p.required and not str(body.params.get(p.name, "")).strip()]
    if missing:
        raise HTTPException(422, f"falta «{missing[0]}»")
    f = _fact(ctx.graph, uuid)
    if not f:
        raise HTTPException(404, "hecho no encontrado")
    if f["invalid_at"] or f["expired_at"]:
        raise HTTPException(409, "el hecho ya no está vigente")
    pr = ctx.db.scalar(select(FactProbe).where(FactProbe.brain_id == ctx.brain.id, FactProbe.fact_uuid == uuid))
    if not pr:
        pr = FactProbe(brain_id=ctx.brain.id, fact_uuid=uuid)
        ctx.db.add(pr)
    pr.verifier, pr.params, pr.created_by = body.verifier, dict(body.params), ctx.user.id
    pr.state, pr.evidence, pr.value, pr.checked_at = None, "", None, None
    ctx.db.commit()
    forget(ctx.brain.id)
    audit(ctx.db, ctx.user, "probe.set", ctx.brain, fact=uuid, verifier=body.verifier)
    return _probe_out(pr)


@router.delete("/facts/{uuid}/probe")
def delete_probe(uuid: str, ctx: BrainCtx = Depends(curator)):
    pr = ctx.db.scalar(select(FactProbe).where(FactProbe.brain_id == ctx.brain.id, FactProbe.fact_uuid == uuid))
    if not pr:
        raise HTTPException(404, "el hecho no tiene sonda")
    ctx.db.delete(pr)
    ctx.db.commit()
    forget(ctx.brain.id)
    audit(ctx.db, ctx.user, "probe.delete", ctx.brain, fact=uuid)
    return {"ok": True}


@router.post("/probes/run", status_code=202)
def run_now(ctx: BrainCtx = Depends(curator)):
    if not ctx.db.scalar(select(func.count()).select_from(FactProbe).where(FactProbe.brain_id == ctx.brain.id)):
        raise HTTPException(409, "el brain no tiene sondas")
    jid = submit(ctx.brain.id, ctx.user.id)
    audit(ctx.db, ctx.user, "probe.run", ctx.brain, job=jid)
    return {"job": jid}
