"""Entorno aislado para toda la suite: nada de lo que escriben los tests toca rutas reales del sistema."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="mimirsynth-tests-")
os.environ.setdefault("MIMIRSYNTH_DOC_STORE", f"{_tmp}/documents")
os.environ.setdefault("MIMIRSYNTH_DOC_ROOTS_BASE", f"{_tmp}/sources")
os.environ.setdefault("MIMIRSYNTH_SESSION_SECRET", "test-secret-not-for-production")
os.environ.setdefault("MIMIRSYNTH_DEFAULT_LANGUAGE", "es")  # la API responde en el idioma de quien llama: los tests comprueban los textos de origen

# The graph tests switch on with MIMIRSYNTH_TEST_FALKOR=host and get the backend the settings choose. With
# MIMIRSYNTH_TEST_NEO4J=bolt://host:7687 (and MIMIRSYNTH_NEO4J_USER / _PASSWORD) the same tests run against Neo4j instead (#357).
if os.environ.get("MIMIRSYNTH_TEST_NEO4J"):
    os.environ["MIMIRSYNTH_GRAPH_BACKEND"] = "neo4j"
    os.environ["MIMIRSYNTH_NEO4J_URI"] = os.environ["MIMIRSYNTH_TEST_NEO4J"]
    os.environ.setdefault("MIMIRSYNTH_TEST_FALKOR", "unused")


# What the default run leaves out (#450): the tests that need a service skip themselves, and a count in the summary says so, since
# "N skipped" alone does not tell a contributor that the graph or PostgreSQL code went untested. CONTRIBUTING.md says how to start them.
SERVICES = (("MIMIRSYNTH_TEST_FALKOR", "a graph database (MIMIRSYNTH_TEST_FALKOR=localhost with a throwaway FalkorDB)"),
            ("MIMIRSYNTH_TEST_PG", "PostgreSQL with pgvector (MIMIRSYNTH_TEST_PG)"))


def service_skips(reasons: list[str]) -> list[tuple[int, str]]:
    """(how many, what they need) for each service some skipped test was waiting for."""
    return [(n, what) for var, what in SERVICES if (n := sum(1 for r in reasons if var in r))]


def pytest_terminal_summary(terminalreporter):
    reasons = [str(r.longrepr[2] if isinstance(r.longrepr, tuple) else r.longrepr) for r in terminalreporter.stats.get("skipped", [])]
    lines = service_skips(reasons)
    if lines:
        terminalreporter.write_sep("-", "tests skipped for lack of a service")
        for n, what in lines:
            terminalreporter.write_line(f"{n} need {what}")
        terminalreporter.write_line("To run them as CI does, see \"Set up the environment\" in CONTRIBUTING.md.")
