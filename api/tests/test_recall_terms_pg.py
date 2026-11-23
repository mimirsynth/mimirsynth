"""The brain's common terms against real PostgreSQL (#459), on a synthetic brain about one subject: a question that only shares the
subject's words with most fragments returns fewer of them, the relevant one; one with a distinctive word still finds it.
Runs ALONE (its own process):  MIMIRSYNTH_TEST_PG=postgresql+psycopg://...   pytest tests/test_recall_terms_pg.py"""
import os

PG = os.environ.get("MIMIRSYNTH_TEST_PG")
if PG:
    os.environ["MIMIRSYNTH_DATABASE_URL"] = PG
    os.environ["MIMIRSYNTH_AUTH_MODE"] = "off"
    os.environ["MIMIRSYNTH_EMBEDDING_DIM"] = "64"

import pytest

pytestmark = pytest.mark.skipif(not PG, reason="necesita PostgreSQL con pgvector (MIMIRSYNTH_TEST_PG)")
BRAIN = 945900
POOL = [f"tema{i:02d}" for i in range(40)]   # each in about 12% of the fragments: not common
RELEVANT = "haproxy balances the acme servers"


def _vocab() -> dict[str, int]:
    return {w: i for i, w in enumerate(["acme", "servers", "haproxy", "balances", "the", *POOL])}


def embed(text: str) -> list[float]:
    """One dimension per word: the cosine of two texts is how many words they share, over their lengths."""
    v, vocab = [0.0] * 64, _vocab()
    for w in text.lower().split():
        v[vocab[w]] += 1.0
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


@pytest.fixture()
def brain():
    from sqlalchemy import text

    from mimirsynth import index, terms
    from mimirsynth.store import engine, init_db
    init_db()
    with engine().begin() as c:   # other tests of the same database may have created them with another dimension
        c.execute(text("DROP TABLE IF EXISTS episode_chunks, doc_chunks CASCADE"))
    index.init_index()
    from mimirsynth import docindex  # noqa: F401  (its table, empty: the passages' corpus has nothing to count)
    index.IndexBase.metadata.create_all(engine())
    texts = [RELEVANT] + [" ".join(["acme", "servers", *(POOL[(i * 5 + k) % 40] for k in range(5))]) for i in range(60)]
    with engine().begin() as c:
        for i, t in enumerate(texts):
            c.execute(text("INSERT INTO episode_chunks (brain_id, episode_uuid, chunk_idx, name, text, valid_at, content_hash, embedding) "
                           "VALUES (:b, :u, 0, '', :t, NULL, 'h', CAST(:e AS vector))"), {"b": BRAIN, "u": f"ep{i}", "t": t, "e": str(embed(t))})
    terms.forget(BRAIN)
    yield
    terms.forget(BRAIN)
    with engine().begin() as c:
        c.execute(text("DELETE FROM episode_chunks WHERE brain_id = :b"), {"b": BRAIN})


def test_the_subject_is_common_and_the_rest_is_not(brain):
    from mimirsynth import terms
    m = terms.measure(BRAIN)
    assert m["chunks"]["texts"] == 61 and m["chunks"]["common"] == {"acme": 1.0, "servers": 1.0}
    assert m["docs"] == {"texts": 0, "common": {}}                                      # too few passages to say anything


def test_a_question_that_only_shares_the_subject_brings_fewer_and_the_relevant_one(brain):
    from mimirsynth import recall as R
    from mimirsynth import terms
    terms.remember(BRAIN, terms.measure(BRAIN))
    q = "acme servers haproxy"
    before = R.search_chunks(BRAIN, embed(q), q, 4, 0.5)
    after = R.search_chunks(BRAIN, embed(q), q, 4, 0.5, common=True)
    assert before[0]["text"] == RELEVANT and len(before) == 4                           # today: three more that only name the subject
    assert [c["text"] for c in after] == [RELEVANT]                                    # the subject's words no longer let them in
    q = "haproxy"   # a distinctive word: found either way (one word of five: similarity 1/√5, so a threshold below it)
    assert [c["text"] for c in R.search_chunks(BRAIN, embed(q), q, 4, 0.4, common=True)] == [RELEVANT]
    assert [c["text"] for c in R.search_chunks(BRAIN, embed(q), q, 4, 0.4)] == [RELEVANT]
