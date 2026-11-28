"""The test suite's own tooling (#450): the summary that counts the tests skipped for lack of a service."""
from conftest import service_skips

REASONS = ["necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)",
           "needs a disposable FalkorDB (MIMIRSYNTH_TEST_FALKOR=host)",
           "necesita PostgreSQL con pgvector (MIMIRSYNTH_TEST_PG) y FalkorDB (MIMIRSYNTH_TEST_FALKOR)",
           "necesita un Neo4j desechable (MIMIRSYNTH_TEST_NEO4J=bolt://host:7687)",
           "needs OpenCode: MIMIRSYNTH_TEST_OPENCODE=<the opencode program>"]


def test_the_summary_counts_the_skips_each_service_would_run():
    got = service_skips(REASONS, {})
    assert [n for n, _ in got] == [3, 1, 1]
    assert "FalkorDB" in got[0][1] and "PostgreSQL" in got[1][1] and "Neo4j" in got[2][1]
    assert service_skips(["the plugin's tests need Node 22.6 or later"], {}) == []


def test_a_service_already_set_is_not_blamed_for_a_skip():
    """With FalkorDB set, a test that needs PostgreSQL too skipped for PostgreSQL alone."""
    got = service_skips(REASONS, {"MIMIRSYNTH_TEST_FALKOR": "localhost"})
    assert [(n, w.split(" (")[0]) for n, w in got] == [(1, "PostgreSQL with pgvector"), (1, "Neo4j")]
