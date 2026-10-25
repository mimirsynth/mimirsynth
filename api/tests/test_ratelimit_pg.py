"""Limitador de peticiones contra PostgreSQL real: varios hilos (como varios procesos) no pueden pasarse del límite.
Se ejecuta SOLO (proceso aparte) con MIMIRSYNTH_TEST_PG=postgresql+psycopg://...   pytest tests/test_ratelimit_pg.py"""
import os
from concurrent.futures import ThreadPoolExecutor

PG = os.environ.get("MIMIRSYNTH_TEST_PG")
if PG:
    os.environ["MIMIRSYNTH_DATABASE_URL"] = PG
    os.environ["MIMIRSYNTH_AUTH_MODE"] = "off"

import pytest  # noqa: E402

pytestmark = pytest.mark.skipif(not PG, reason="necesita PostgreSQL (MIMIRSYNTH_TEST_PG)")


def test_concurrent_attempts_never_exceed_the_limit():
    from mimirsynth import ratelimit
    from mimirsynth.store import init_db
    init_db()
    ratelimit.reset()
    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(lambda _: ratelimit._allow_db("conc", 10, 600), range(80)))  # _allow_db: que un fallo no se disfrace de memoria
    assert sum(results) == 10
    assert ratelimit._allow_db("conc", 10, 600) is False
    ratelimit.reset()
