"""The test suite's own tooling (#450): the summary that counts the tests skipped for lack of a service."""
from conftest import service_skips


def test_the_summary_counts_the_skips_each_service_would_run():
    reasons = ["necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)",
               "needs a disposable FalkorDB (MIMIRSYNTH_TEST_FALKOR=host)",
               "necesita PostgreSQL con pgvector (MIMIRSYNTH_TEST_PG) y FalkorDB (MIMIRSYNTH_TEST_FALKOR)",
               "needs OpenCode: MIMIRSYNTH_TEST_OPENCODE=<the opencode program>"]
    got = service_skips(reasons)
    assert [n for n, _ in got] == [3, 1]
    assert "FalkorDB" in got[0][1] and "PostgreSQL" in got[1][1]
    assert service_skips(["the plugin's tests need Node 22.6 or later"]) == []
