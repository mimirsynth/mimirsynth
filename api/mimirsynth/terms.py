"""The common terms of a brain (#459): the words that appear in so many of its texts that matching them says nothing.

In a brain about one subject, the subject's name is in a large share of its episode fragments and document passages. A question whose
only distinctive word is that name matched hundreds of them by text and filled the context with noise. With the daily health run
(`measure`), each brain counts in how many of its fragments, and in how many passages of its active documents, each term appears, and
keeps the ones in more than COMMON_SHARE of either. With `recall_common_terms` on, the recall leaves them out of the keyword part of
the hybrid search (they stay in the vector part, so the meaning of the question does not change) and does not count them toward the
two shared terms that let a text in with a little less similarity.

A brain with fewer than MIN_TEXTS texts in a corpus has no common terms in it: a share of a handful says little. A brain not measured
yet, or whose last measurement is older than STORED_DAYS, has none either, and its recall is what it was.
"""
import threading
import time
from datetime import timedelta

from sqlalchemy import select, text

COMMON_SHARE = 0.20   # a term in more than this share of a corpus is common
MIN_TEXTS = 50        # texts a corpus needs before a share says something
MAX_TERMS = 200       # common terms kept per corpus, the most frequent first
CACHE_SECONDS = 600   # what a process keeps in memory before reading the stored measurement again
STORED_DAYS = 2       # a stored measurement older than this is not used

_CORPORA = {   # the texts of each corpus, for `ts_stat`; `{b}` is the brain's id, an integer
    "chunks": "SELECT tsv FROM episode_chunks WHERE brain_id = {b}",
    "docs": "SELECT c.tsv FROM doc_chunks c JOIN documents d ON d.id = c.document_id WHERE c.brain_id = {b} AND d.status = 'active'",
}
_cache: dict[int, tuple[float, dict]] = {}
_lock = threading.Lock()


def measure(brain_id: int) -> dict:
    """The common terms of each corpus of a brain, with how many texts it has: `{"chunks": {"texts": n, "common": {term: share}}, …}`.
    Without the text index (no PostgreSQL), nothing."""
    from . import index
    from .store import engine
    if not index.enabled():
        return {}
    b = int(brain_id)   # ts_stat takes its query as text: the id is the only thing put in it, and it is an integer
    out = {}
    with engine().begin() as c:
        for name, sql in _CORPORA.items():
            n = c.execute(text(f"SELECT count(*) FROM ({sql.format(b=b)}) t")).scalar() or 0
            common = {}
            if n >= MIN_TEXTS:
                for word, ndoc in c.execute(text("SELECT word, ndoc FROM ts_stat(:q) WHERE ndoc > :min ORDER BY ndoc DESC, word LIMIT :k"),
                                            {"q": sql.format(b=b), "min": COMMON_SHARE * n, "k": MAX_TERMS}):
                    common[word] = round(ndoc / n, 3)
            out[name] = {"texts": n, "common": common}
    return out


def remember(brain_id: int, m: dict) -> None:
    """Keeps a fresh measurement in memory, so the recall uses it at once."""
    with _lock:
        _cache[brain_id] = (time.monotonic(), m)


def forget(brain_id: int | None = None) -> None:
    with _lock:
        if brain_id is None:
            _cache.clear()
        else:
            _cache.pop(brain_id, None)


def _stored(brain_id: int) -> dict:
    from .health import _today
    from .models import HealthRun
    from .store import _factory
    with _factory()() as db:
        run = db.scalar(select(HealthRun).where(HealthRun.brain_id == brain_id, HealthRun.status == "done",
                                                HealthRun.day >= _today() - timedelta(days=STORED_DAYS)).order_by(HealthRun.day.desc()).limit(1))
        return ((run.metrics or {}).get("terms") or {}) if run else {}


def common(brain_id: int) -> dict[str, frozenset[str]]:
    """The common terms of each corpus of a brain (`chunks`, `docs`), from memory or from its last health run. None measured: empty."""
    with _lock:
        hit = _cache.get(brain_id)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        m = hit[1]
    else:
        try:
            m = _stored(brain_id)
        except Exception:  # noqa: BLE001  (without it the recall is what it was before)
            m = {}
        remember(brain_id, m)
    return {k: frozenset((m.get(k) or {}).get("common") or {}) for k in _CORPORA}
