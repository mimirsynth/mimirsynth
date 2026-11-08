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
