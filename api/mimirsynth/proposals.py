"""Cuarentena de aportaciones: los colaboradores proponen, los curadores aprueban o rechazan.

Una aportación aprobada queda lista para ingerir (extracción con Graphiti); eso es el paso siguiente.
"""
import re
import unicodedata
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import String, case, cast, func, select, update

from . import claims as claims_mod, deciders_admin, ingest, secretguard
from .deps import BrainCtx, audit, brain_access
from .i18n import language, tr
from .models import Job, Proposal, User
from .roles import allows

router = APIRouter(prefix="/api/brains/{slug}/proposals")
contributor = brain_access("contributor")
curator = brain_access("curator")
UNDO_SECONDS = 10  # how long a person's approval waits before ingestion starts, so it can be undone
STATUSES = {"pending", "approved", "rejected", "ingested", "failed"}
KINDS = {"memory", "correction"}  # adds knowledge | invalidates a fact (#109)


class ProposalIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=50000)
    source: str = Field("text", pattern="^(text|message|json)$")
    source_description: str = Field("", max_length=255)
    reference_time: datetime | None = None
    confidence: float | None = Field(None, ge=0, le=1)
    origin: str | None = Field(None, pattern="^(agent|auto)$", description="agent: an agent chose to write it; auto: captured automatically. Empty: auto. Never above the token's max_trust (#298).")
    claims: list[claims_mod.ClaimIn] = Field(default_factory=list, max_length=claims_mod.MAX,
                                             description="Structured claims next to the text (#295): compared with what the brain knows when sent.")


class ReviewIn(BaseModel):
    note: str = Field("", max_length=2000)


def _out(p: Proposal, full: bool = False) -> dict:
    d = {"id": p.id, "name": p.name, "source": p.source, "source_description": p.source_description, "confidence": p.confidence,
         "status": p.status, "author": p.author.email or p.author.name, "author_name": p.author.name or p.author.email, "created_at": p.created_at, "reviewed_at": p.reviewed_at,
         "reviewer": (p.reviewer.email or p.reviewer.name) if p.reviewer else None,
         "review_note": p.review_note, "reference_time": p.reference_time, "review_kind": p.review_kind, "decision": p.decision,
         "ingest_error": p.ingest_error, "ingest_report": p.ingest_report, "episode_uuid": p.episode_uuid, "ingested_at": p.ingested_at,
         "secrets": secretguard.describe(p.secret_findings), "kind": p.kind or "memory", "related_verdict": p.related_verdict or "", "correction": p.correction, "claims": p.claims, "category": p.category or "", "origin": p.origin or "", "selftest": p.selftest, "purged_at": p.purged_at}
    d["body"] = p.body if full else p.body[:300]
    return d


@router.post("", status_code=201)
def submit(body: ProposalIn, request: Request, bg: BackgroundTasks, ctx: BrainCtx = Depends(contributor)):
    """Colaborador: entra en cuarentena (pending). Curador o superior: aprobada directamente, queda en el registro.
    `secrets_notice` tells the author, in their language, what the secret detector masked or flagged (empty when nothing)."""
    p = create(ctx, request, bg, body)
    return {**_out(p), "secrets_notice": secretguard.notice(p.secret_findings, language(request))}


def create(ctx: BrainCtx, request: Request, bg: BackgroundTasks, body: ProposalIn) -> Proposal:
    """Alta de una propuesta (también la usa `remember` del MCP). Antes de guardar pasa por el detector de secretos del brain (#116)."""
    try:
        name, in_name = secretguard.guard(ctx.brain, body.name)
        text, in_body = secretguard.guard(ctx.brain, body.body)
    except secretguard.Blocked:
        rules = sorted({r for t in (body.name, body.body) for r in _blocked_rules(ctx, t)})
        audit(ctx.db, ctx.user, "proposal.blocked", ctx.brain, reason="secrets", rules=rules)
        labels = secretguard.labels(language(request))
        raise HTTPException(422, tr("La propuesta contiene secretos ({{labels}}). Quítalos y guarda solo dónde están (por ejemplo, en qué gestor de contraseñas).",
                                    language(request), labels=", ".join(labels[r] for r in rules)))
    checked = _claims(ctx, request, body)
    tok = getattr(request.state, "token", None)
    from .trust import effective_origin
    return store(ctx.db, ctx.brain, ctx.user, body, name, text, in_name, in_body, allows(ctx.role, "curator"), bg.add_task,
                 token_id=tok.id if tok else None, claims=checked, origin=effective_origin(body.origin, tok))


def _claims(ctx: BrainCtx, request: Request, body: ProposalIn) -> list[dict] | None:
    """The proposal's claims through the secret detector and compared with the brain's current facts (#295)."""
    if not body.claims:
        return None
    from .conflicts import _brain_functional
    from .vocab import alias_map
    lang = language(request)
    out = []
    for c in body.claims:
        d = c.model_dump(mode="json")
        if c.valid_from:   # the graph's format, as a correction stores its date
            d["valid_from"] = (c.valid_from if c.valid_from.tzinfo else c.valid_from.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
        for k in ("subject", "value"):
            try:
                d[k] = secretguard.guard(ctx.brain, d[k])[0]
            except secretguard.Blocked:
                raise HTTPException(422, tr("Una afirmación contiene secretos. Quítalos y guarda solo dónde están (por ejemplo, en qué gestor de contraseñas).", lang)) from None
        out.append(d)
    try:
        return claims_mod.check(ctx.graph, out, alias_map(ctx.db, ctx.brain.id), _brain_functional(ctx.db, ctx.brain.id))
    except claims_mod.ClaimError as e:
        if e.code == "unknown":
            raise HTTPException(404, tr("No hay ningún hecho con el uuid {{uuid}} en este brain.", lang, uuid=e.uuid)) from None
        raise HTTPException(409, tr("El hecho {{uuid}} ya no está vigente: una afirmación no puede sustituirlo.", lang, uuid=e.uuid)) from None


def store(db, brain, user, body: ProposalIn, name: str, text: str, in_name: list, in_body: list, direct: bool, later,
          token_id: int | None = None, how: str = "direct", claims: list[dict] | None = None, origin: str = "") -> Proposal:
    """Saves a proposal whose name and text already went through the secret detector (`in_name`, `in_body`: its findings). `direct`
    approves it, unless the detector flagged something; otherwise the decider triages it, through `later` (a background task)."""
    found = [{**f, "field": "name"} for f in in_name] + [{**f, "field": "body"} for f in in_body]
    direct = direct and not secretguard.flagged(found)  # con algo marcado, ni el curador que la envía la aprueba sin mirarla
    p = Proposal(brain_id=brain.id, author_id=user.id, token_id=token_id, name=name[:255], body=text, source=body.source,
                 source_description=body.source_description, reference_time=body.reference_time, confidence=body.confidence,
                 status="approved" if direct else "pending", secret_findings=found or None, claims=claims, origin=origin)
    if direct:
        p.reviewer_id, p.reviewed_at, p.review_kind = user.id, datetime.now(timezone.utc), how
    db.add(p); db.commit()
    audit(db, user, "proposal.submit", brain, id=p.id, status=p.status, name=secretguard.safe_name(p), **({"secrets": found} if found else {}))
    if direct and ingest.enabled():
        ingest.submit_ingest(p.id, brain.id, secretguard.safe_name(p), user.id)
    elif not direct:
        later(check_related, p.id)  # what the brain already knows close to it, for the queue's order and the batch
        later(deciders_admin.triage_proposal, p.id)  # sin decisor configurado no hace nada; con secretos marcados, tampoco
    return p


def _blocked_rules(ctx: BrainCtx, text: str) -> list[str]:
    try:
        secretguard.guard(ctx.brain, text)
    except secretguard.Blocked as e:
        return e.rules
    return []


_AUTHOR = func.coalesce(func.nullif(User.name, ""), User.email)  # a person's name as the history shows it: its filter and its order
_SORTS = {"id": Proposal.id, "name": Proposal.name, "author": _AUTHOR, "conf": Proposal.confidence, "at": Proposal.created_at, "decided": Proposal.reviewed_at}  # «Enviada» by its date: an imported proposal's id is later than its date
# the review queue's order: what most needs a person first (corrections, then flagged secrets, then what the brain already knows as
# nearly the same or as no longer true, then low declared confidence), oldest first inside each group, so nothing waits forever behind
# newer arrivals
LOW_CONFIDENCE = 0.6
KNOWN = ("duplicate", "stale")  # what the brain already knows: never approved in a batch, and the A key asks first
_RISK = case((Proposal.kind == "correction", 0), (cast(Proposal.secret_findings, String).like('%"flagged"%'), 1),
             (Proposal.related_verdict.in_(KNOWN), 2), (Proposal.confidence < LOW_CONFIDENCE, 3), else_=4)
BULK_MAX = 200


@router.get("")
def list_proposals(bg: BackgroundTasks, status: str | None = None, kind: str | None = None, q: str = Query("", max_length=200), author: int | None = None,
                   sort: str = "at", order: str = "desc", limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), mine: bool = False,
                   ctx: BrainCtx = Depends(contributor)):
    """Los curadores ven todas; un colaborador solo las suyas. Paginado en el servidor (#88): `total` cuenta lo que pasa los filtros
    y `authors` lista los autores visibles para el filtro de la columna. `kind` keeps only memories or only corrections. `status=decided`
    keeps everything but the pending ones (the review history); `mine` only the caller's own; `sort=risk` is the review queue's order."""
    if status and status not in STATUSES and status != "decided":
        raise HTTPException(400, "estado inválido")
    if kind and kind not in KINDS:
        raise HTTPException(400, "tipo inválido")
    if sort not in _SORTS and sort != "risk":
        raise HTTPException(400, "orden inválido")
    base = select(Proposal).join(User, User.id == Proposal.author_id).where(Proposal.brain_id == ctx.brain.id)
    if mine or not allows(ctx.role, "curator"):
        base = base.where(Proposal.author_id == ctx.user.id)
    authors = ctx.db.execute(base.with_only_columns(User.id, _AUTHOR).distinct().order_by(_AUTHOR)).all()
    if status == "decided":
        base = base.where(Proposal.status != "pending")
    elif status:
        base = base.where(Proposal.status == status)
    if kind:
        base = base.where(Proposal.kind == kind)
    if author:
        base = base.where(Proposal.author_id == author)
    if q.strip():
        base = base.where(Proposal.name.ilike("%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"))
    total = ctx.db.scalar(select(func.count()).select_from(base.subquery()))
    if sort == "risk":  # `order=desc` turns the whole queue around (newest and least risky first)
        keys = (_RISK.asc(), Proposal.created_at.asc(), Proposal.id.asc()) if order == "asc" else (_RISK.desc(), Proposal.created_at.desc(), Proposal.id.desc())
    else:
        keys = ((_SORTS[sort].asc() if order == "asc" else _SORTS[sort].desc()).nulls_last(), Proposal.id.desc())
    rows = ctx.db.scalars(base.order_by(*keys).limit(limit).offset(offset)).all()
    if status == "pending" and allows(ctx.role, "curator") and ingest.enabled() and ctx.db.scalar(select(func.count()).select_from(_unchecked(ctx.brain.id).subquery())):
        bg.add_task(check_unchecked, ctx.brain.id)  # the queue ranks by what the brain knows: what was never checked is checked now
    return {"total": total, "limit": limit, "offset": offset, "authors": [{"id": i, "name": n} for i, n in authors], "items": [_out(p) for p in rows]}


@router.get("/counts")
def counts(kind: str | None = None, mine: bool = False, ctx: BrainCtx = Depends(contributor)):
    """Número de propuestas por estado (un colaborador solo cuenta las suyas), only of one `kind` when given.
    `kinds` counts each kind across every state, `kinds_in` each kind inside each state (and «all», «decided»), and
    `corrections_pending` the corrections a person still has to decide."""
    if kind and kind not in KINDS:
        raise HTTPException(400, "tipo inválido")
    q = select(Proposal.status, Proposal.kind, func.count()).where(Proposal.brain_id == ctx.brain.id).group_by(Proposal.status, Proposal.kind)
    if mine or not allows(ctx.role, "curator"):
        q = q.where(Proposal.author_id == ctx.user.id)
    rows = [(st, k or "memory", n) for st, k, n in ctx.db.execute(q)]
    out: dict = {k: 0 for k in sorted(STATUSES)}
    for st, k, n in rows:
        if not kind or k == kind:
            out[st] += n
    out["all"] = sum(out[k] for k in STATUSES)
    out["decided"] = out["all"] - out["pending"]
    out["kinds"] = {k: sum(n for _, kk, n in rows if kk == k) for k in sorted(KINDS)}
    # each kind inside each state (and inside «all» and «decided»), so a kind's count matches the state on screen
    groups = {st: {st} for st in STATUSES} | {"all": set(STATUSES), "decided": set(STATUSES) - {"pending"}}
    out["kinds_in"] = {g: {k: sum(n for st, kk, n in rows if kk == k and st in sts) for k in sorted(KINDS)} for g, sts in groups.items()}
    out["corrections_pending"] = sum(n for st, k, n in rows if st == "pending" and k == "correction")
    return out


def _get(ctx: BrainCtx, pid: int) -> Proposal:
    p = ctx.db.get(Proposal, pid)
    if not p or p.brain_id != ctx.brain.id:
        raise HTTPException(404, "propuesta no encontrada")
    return p


@router.get("/{pid}")
def get_proposal(pid: int, ctx: BrainCtx = Depends(contributor)):
    p = _get(ctx, pid)
    if p.author_id != ctx.user.id and not allows(ctx.role, "curator"):
        raise HTTPException(404, "propuesta no encontrada")
    return _out(p, full=True)


def _review(ctx: BrainCtx, pid: int, status: str, note: str, also: tuple[str, ...] = ()) -> dict:
    """A person's decision on a pending proposal (or one in `also`)."""
    p = _get(ctx, pid)
    if p.status != "pending" and p.status not in also:
        raise HTTPException(409, f"la propuesta ya está {p.status}")
    p.status, p.reviewer_id, p.reviewed_at, p.review_note, p.review_kind = status, ctx.user.id, datetime.now(timezone.utc), note, "human"
    ctx.db.commit()
    audit(ctx.db, ctx.user, f"proposal.{status}", ctx.brain, id=p.id, note=note)
    return _out(p)


@router.post("/{pid}/approve")
def approve(pid: int, body: ReviewIn, request: Request, bg: BackgroundTasks, ctx: BrainCtx = Depends(curator)):
    p = _get(ctx, pid)
    if p.status == "pending" and secretguard.flagged(p.secret_findings):  # what the detector flagged never enters as written: «mask-and-approve»
        raise HTTPException(409, "la propuesta tiene secretos por revisar: enmascáralos al aprobarla")
    if p.kind == "correction":  # applied on approval, and only approved if it could be applied (#109)
        from . import corrections
        if p.status != "pending":
            raise HTTPException(409, f"la propuesta ya está {p.status}")
        corrections.apply(ctx, p, language(request), note=body.note)
        return _out(p)
    out = _review(ctx, pid, "approved", body.note)
    if ingest.enabled() or claims_mod.actions_only(_get(ctx, pid)):  # a person's approval waits UNDO_SECONDS queued: the curator can still take it back (`undo`)
        ingest.submit_ingest(pid, ctx.brain.id, secretguard.safe_name(_get(ctx, pid)), ctx.user.id, delay=UNDO_SECONDS)
        out["undo_seconds"] = UNDO_SECONDS
    return out


@router.post("/{pid}/mask-and-approve")
def mask_and_approve(pid: int, body: ReviewIn, request: Request, bg: BackgroundTasks, ctx: BrainCtx = Depends(curator)):
    """For a proposal with secrets flagged for review, the only way in: masks every flagged span of its title and text (as the
    brain's «mask» mode would have done), audits which kinds were masked (never the values) and approves it like any other. A
    proposal approved as written could carry a live credential into the permanent memory."""
    p = _get(ctx, pid)
    if p.status != "pending":
        raise HTTPException(409, f"la propuesta ya está {p.status}")
    if not secretguard.flagged(p.secret_findings):
        raise HTTPException(409, "la propuesta no tiene secretos por revisar")
    found = p.secret_findings or []
    rules = sorted({f["rule"] for f in found if f.get("action") == "flagged"})
    lang = secretguard.instance_lang()
    texts = {"name": p.name, "body": p.body, "reason": (p.correction or {}).get("reason") or ""}  # a correction's reason is guarded too
    where = lambda f: f.get("field") or "body"  # noqa: E731
    masked, findings = {}, [f for f in found if where(f) not in texts]
    for field, text in texts.items():
        if mine := [f for f in found if where(f) == field]:
            masked[field], new = secretguard.mask_flagged(text, mine, lang)
            findings += new
    p.name, p.body, p.secret_findings = masked.get("name", p.name)[:255], masked.get("body", p.body), findings
    if "reason" in masked:
        p.correction = {**p.correction, "reason": masked["reason"]}
    ctx.db.commit()
    audit(ctx.db, ctx.user, "proposal.secrets_masked", ctx.brain, id=p.id, rules=rules)
    return approve(pid, body, request, bg, ctx)


@router.post("/{pid}/ingest")
def retry_ingest(pid: int, bg: BackgroundTasks, ctx: BrainCtx = Depends(curator)):
    """Lanza (o reintenta) la ingesta de una propuesta aprobada o fallida."""
    if not ingest.enabled():
        raise HTTPException(503, "ingesta no configurada (MIMIRSYNTH_LLM_BASE_URL y MIMIRSYNTH_LLM_MODEL)")
    p = _get(ctx, pid)
    if p.status not in ("approved", "failed") or (p.kind == "correction" and not p.body.strip()):
        raise HTTPException(409, f"la propuesta está {p.status}")
    return {"queued": True, "job": ingest.submit_ingest(pid, ctx.brain.id, secretguard.safe_name(p), ctx.user.id)}


@router.post("/{pid}/reject")
def reject(pid: int, body: ReviewIn, ctx: BrainCtx = Depends(curator)):
    """Rejects a pending proposal, or one whose ingestion failed and that the curator gives up on instead of retrying. For a failed one,
    a retry still waiting is cancelled, and one already running wins: what it writes is corrected by invalidating its facts."""
    p = _get(ctx, pid)
    if p.status == "failed":
        key = f"proposal.ingest:{pid}"
        ctx.db.execute(update(Job).where(Job.dedupe_key == key, Job.status == "queued")
                       .values(status="cancelled", finished_at=datetime.now(timezone.utc), error="propuesta rechazada por un curador"))
        if ctx.db.scalar(select(Job.id).where(Job.dedupe_key == key, Job.status == "running")):
            ctx.db.rollback()
            raise HTTPException(409, "la ingesta se está reintentando: espera a que termine")
        out = _review(ctx, pid, "rejected", body.note, also=("failed",))
        from . import notify
        notify.resolve("ingest.failed", f"proposal:{pid}")  # nothing is left to fix
        return out
    return _review(ctx, pid, "rejected", body.note)


class BulkIn(BaseModel):
    verb: str = Field(pattern="^(approve|reject)$")
    ids: list[int] = Field(min_length=1, max_length=BULK_MAX)
    note: str = Field("", max_length=2000)


@router.post("/bulk")
def bulk(body: BulkIn, ctx: BrainCtx = Depends(curator)):
    """One decision for several proposals the curator selected. Each is decided as if alone (same audit, same 10 s grace before ingestion);
    what cannot be decided this way is skipped and said why: not pending any more, or, for approving, a correction, a proposal with a
    secret to review, one the brain already knows (nearly the same, or no longer true) or one very close to a current fact, which a person
    reads and decides one at a time."""
    done, skipped = [], []
    for pid in dict.fromkeys(body.ids):
        p = ctx.db.get(Proposal, pid)
        if not p or p.brain_id != ctx.brain.id:
            skipped.append({"id": pid, "reason": "not_found"}); continue
        if p.status != "pending":
            skipped.append({"id": pid, "reason": "not_pending"}); continue
        if body.verb == "approve" and p.kind == "correction":
            skipped.append({"id": pid, "reason": "correction"}); continue
        if body.verb == "approve" and claims_mod.replaces(p):  # it invalidates facts: one at a time, like a correction (#295)
            skipped.append({"id": pid, "reason": "replaces"}); continue
        if body.verb == "approve" and any(f.get("action") == "flagged" for f in (p.secret_findings or [])):
            skipped.append({"id": pid, "reason": "secret"}); continue
        if body.verb == "approve" and p.related_verdict in KNOWN:
            skipped.append({"id": pid, "reason": "known"}); continue
        if body.verb == "approve" and p.related_verdict == "similar":  # adds a little to a current fact: read it before approving
            skipped.append({"id": pid, "reason": "close"}); continue
        if body.verb == "approve" and unchecked(p):
            skipped.append({"id": pid, "reason": "unchecked"}); continue
        _review(ctx, pid, "approved" if body.verb == "approve" else "rejected", body.note)
        if body.verb == "approve" and ingest.enabled():
            ingest.submit_ingest(pid, ctx.brain.id, secretguard.safe_name(p), ctx.user.id, delay=UNDO_SECONDS)
        done.append(pid)
    out = {"done": done, "skipped": skipped}
    if body.verb == "approve" and done and ingest.enabled():
        out["undo_seconds"] = UNDO_SECONDS
    return out


RELATED_FACTS = 5
# How close a known fact is to a proposal, for the reviewer. A proposal repeats a fact only when it adds nothing to it: no word of
# content that the fact does not have. A proposal about one night's failed backup contains the words of «the nightly backup goes to the
# external bucket» and adds what happened; «the wiki uses PostgreSQL, in the same container» adds where it runs. Both are new knowledge,
# however close their embeddings are, so the similarity alone never makes a duplicate: it only makes a fact «close».
REPEATS_SCORE, CLOSE_SCORE, REPEATS_WORDS = 0.95, 0.85, 0.8
# A word of content is four letters or more, or anything with a digit (14, 128, 3): a changed number is often what a proposal adds. An
# identifier is one word (pve-norte-02, nas01.lab): its pieces are not words of their own. Words are compared without accents and by a
# light stem, so «replica» and «replicar», «certificado» and «certificados» are the same word.
_WORD = re.compile(r"\w(?:[\w.-]*\w)?")
# Endings taken off a word to compare it, the longest first; the stem keeps at least four letters. Light on purpose: it has to agree in
# the web (`web/src/pages/Proposals.tsx`, STEM_ENDS), and it only has to tell that two forms are the same word.
STEM_ENDS = ("aciones", "acion", "amente", "mente", "ando", "iendo", "ados", "adas", "idos", "idas", "ado", "ada", "ido", "ida", "an", "en",
             "ar", "er", "ir", "es", "s", "a", "o", "e")
# Words of four letters or more that say nothing about the content, in the two interface languages. The web marks what a proposal adds
# with the same list (`web/src/pages/Proposals.tsx`, STOP): keep them together.
STOP = frozenset("""
como para desde entre sobre pero tras hasta cuando donde porque aunque mientras según durante este esta estos estas esos esas aquel
aquella todo toda todos todas otro otra otros otras cada mucho mucha muchos muchas poco poca algo nada también tampoco solo sólo ahora
antes después luego aquí allí allá está están estaba estaban será serán sido siendo había habían tiene tienen tenía puede pueden hace
hacen sigue siguen queda quedan mismo misma mismos mismas their there these those this that with from have been were into than then also some when where which
what about will would should could while after before other more most only such very
""".split())


def _fold(word: str) -> str:
    """Lower case, without accents."""
    return "".join(c for c in unicodedata.normalize("NFKD", word.lower()) if not unicodedata.combining(c))


def _stem(word: str) -> str:
    """The word without its endings, taken off until none is left (an identifier or a number stays as it is): «copias», «copia» → «copi»."""
    if not word.isalpha():
        return word
    while True:
        end = next((e for e in STEM_ENDS if word.endswith(e) and len(word) - len(e) >= 4), None)
        if not end:
            return word
        word = word[: -len(end)]


_STOP = frozenset(_fold(w) for w in STOP)
_RANK = {"repeats": 0, "close": 1, "related": 2}


def _words(text: str | None) -> set[str]:
    """The words of content of a text, folded and stemmed, to compare it with another one."""
    out = set()
    for w in _WORD.findall(text or ""):
        w = _fold(w)
        if (len(w) >= 4 or any(c.isdigit() for c in w)) and w not in _STOP:
            out.add(_stem(w))
    return out


def relevance(fact: str | None, proposal_words: set[str], score: float | None) -> str:
    """«repeats»: the proposal says it again and adds nothing (the fact's words, or nearly identical embeddings, and no word of content the
    fact lacks); «close»: very similar but it adds something, or a high similarity; «related»: what the recall brought, no more."""
    fw = _words(fact)
    contains = len(fw) >= 3 and len(fw & proposal_words) / len(fw) >= REPEATS_WORDS  # the fact's words are in the proposal
    adds = bool(proposal_words - fw)                                                   # and it says something the fact does not
    if (contains or (score or 0) >= REPEATS_SCORE) and not adds:
        return "repeats"
    return "close" if contains or (score or 0) >= CLOSE_SCORE else "related"


def related_facts(brain, p: Proposal) -> list[dict]:
    """The facts a recall of the proposal's title and text brings back, each with its relevance, what it repeats first. Facts only (no
    fragments, no documents), and not logged for the recall ratings: it is a read for the reviewer, not an agent's recall."""
    from . import recall as recall_mod
    if p.purged_at or not (p.body or "").strip():
        return []
    query = f"{p.name}. {p.body}"[:1500]
    out = recall_mod.recall(brain.id, brain.graph_name, query, RELATED_FACTS, 0, 4000, n_docs=0, min_similarity=0)  # the closest, however far
    keys = ("uuid", "fact", "name", "source", "target", "source_uuid", "target_uuid", "valid_at", "invalid_at", "status", "score")
    words = _words(query)
    facts = [{**{k: f.get(k) for k in keys}, "relevance": relevance(f.get("fact"), words, f.get("score")), "mostly_new": mostly_new(f.get("fact"), words)}
             for f in out.get("facts", [])]
    return sorted(facts, key=lambda f: (_RANK[f["relevance"]], -(f["score"] or 0)))  # what it repeats first, then the closest


def mostly_new(fact: str | None, proposal_words: set[str]) -> bool:
    """More than half of the proposal's words of content are not in the fact: it says something else, however close they are."""
    return bool(proposal_words) and len(proposal_words - _words(fact)) > len(proposal_words) / 2


def verdict(facts: list[dict]) -> str:
    """One word for the queue: «duplicate» when a current fact says nearly the same, «stale» when a close one stopped being true,
    «similar» when a current fact is very close and the proposal adds a little to it, «related» when there is only something near (or
    the proposal is mostly new against it), «new» when nothing is. Only «duplicate» and «stale» are known (`KNOWN`): kept out of a batch, and asked about before approving."""
    if any(f["relevance"] == "repeats" and not f.get("invalid_at") for f in facts):
        return "duplicate"
    # close to something no longer true, and saying mostly the same: a proposal that is mostly new (a backup that failed, against «the
    # backup went only to the NAS») does not put the old fact back
    if any(f.get("invalid_at") and (f["relevance"] == "repeats" or (f["relevance"] == "close" and not f.get("mostly_new"))) for f in facts):
        return "stale"
    # very close to something still true, and adding little to it: a proposal mostly new against the fact only shares its subject
    if any(f["relevance"] == "close" and not f.get("invalid_at") and not f.get("mostly_new") for f in facts):
        return "similar"
    return "related" if facts else "new"


def check_related(pid: int) -> None:
    """In the background after a proposal arrives: stores what the brain already knows close to it, so the review queue can rank it
    and the batch can leave it aside without a recall per row. A failure leaves it unchecked: the detail checks again when opened."""
    from .models import Brain
    from .store import _factory
    with _factory()() as db:
        p = db.get(Proposal, pid)
        if not p or p.status != "pending" or p.kind == "correction" or not ingest.enabled():
            return  # without an extraction engine nothing reaches the graph, so there is nothing to compare with
        try:
            v = verdict(related_facts(db.get(Brain, p.brain_id), p))
        except Exception:  # noqa: BLE001 — no engine or graph yet: nothing to rank by
            return
        p.related_verdict = v
        db.commit()


def unchecked(p: Proposal) -> bool:
    """A pending proposal that adds knowledge whose closeness to what the brain knows was never checked (it arrived without an extraction
    engine, before the check existed, or the check failed): nobody can tell yet whether it repeats something, so a batch leaves it aside.
    Without an extraction engine nothing reaches the graph, so there is nothing to wait for."""
    return p.status == "pending" and p.kind != "correction" and not p.purged_at and not p.related_verdict and ingest.enabled()


def _unchecked(brain_id: int):
    return select(Proposal.id).where(Proposal.brain_id == brain_id, Proposal.status == "pending", Proposal.kind != "correction",
                                     Proposal.purged_at.is_(None), func.coalesce(Proposal.related_verdict, "") == "")


UNCHECKED_BATCH = 100  # checked per pass; the next look at the queue goes on with the rest
_checking: set[int] = set()  # brains with a pass running, so opening the queue twice does not check the same proposals twice


def check_unchecked(brain_id: int) -> None:
    """In the background, when a curator opens the queue: checks the pending proposals whose verdict is missing, oldest first, so the
    queue's order and the batch know about all of them, not only about those someone opened."""
    from .store import _factory
    if brain_id in _checking:
        return
    _checking.add(brain_id)
    try:
        with _factory()() as db:
            ids = db.scalars(_unchecked(brain_id).order_by(Proposal.created_at.asc(), Proposal.id.asc()).limit(UNCHECKED_BATCH)).all()
        for pid in ids:
            check_related(pid)
    finally:
        _checking.discard(brain_id)


@router.get("/{pid}/related")
def related(pid: int, ctx: BrainCtx = Depends(curator)):
    """What the brain already knows close to a proposal: the facts a recall of its title and text brings back, for the curator to check
    it against (a duplicate, a contradiction, or nothing at all: new knowledge). It is a read for the reviewer, not an agent's recall, so it
    is not logged for the recall ratings. Opening it refreshes the verdict the queue ranks by."""
    p = _get(ctx, pid)
    try:
        facts = related_facts(ctx.brain, p)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"no se pudo buscar lo relacionado: {e}") from e
    if p.status == "pending" and p.kind != "correction" and not p.purged_at and (v := verdict(facts)) != p.related_verdict:
        p.related_verdict = v
        ctx.db.commit()
    return {"facts": facts}


@router.post("/{pid}/undo")
def undo(pid: int, ctx: BrainCtx = Depends(curator)):
    """Takes a person's decision back: the proposal is pending again. A rejection can always be reopened (unless its text was purged); an
    approval only while its ingestion has not started (the grace period after approving, or when there is no extraction engine). Once
    ingestion starts, what reached the graph is corrected by invalidating its facts, as anything else in the memory. Corrections, applied on
    approval, are undone with «Reactivar el hecho»."""
    p = _get(ctx, pid)
    if p.status == "rejected":
        if p.purged_at:
            raise HTTPException(409, "el texto de esta propuesta se purgó por el plazo de retención: no se puede reabrir")
    elif p.status == "approved" and p.kind != "correction":
        key = f"proposal.ingest:{pid}"
        # only a job still waiting is cancelled, in one conditional update (jobs._run claims it the same way): whichever commits first wins,
        # so an ingestion that has started is never interrupted
        ctx.db.execute(update(Job).where(Job.dedupe_key == key, Job.status == "queued")
                       .values(status="cancelled", finished_at=datetime.now(timezone.utc), error="aprobación deshecha por un curador"))
        if ctx.db.scalar(select(Job.id).where(Job.dedupe_key == key, Job.status == "running")):
            ctx.db.rollback()
            raise HTTPException(409, "la ingesta ya ha empezado: lo que entre en el grafo se corrige invalidando sus hechos")
    else:
        raise HTTPException(409, f"la propuesta está {p.status}: no hay decisión que deshacer")
    was = p.status
    p.status, p.reviewer_id, p.reviewed_at, p.review_note, p.review_kind = "pending", None, None, "", ""
    ctx.db.commit()
    audit(ctx.db, ctx.user, "proposal.reopened" if was == "rejected" else "proposal.approval_undone", ctx.brain, id=p.id)
    return _out(p)
