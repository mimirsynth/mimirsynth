"""Entorno aislado para toda la suite: nada de lo que escriben los tests toca rutas reales del sistema."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="mimirsynth-tests-")
os.environ.setdefault("MIMIRSYNTH_DOC_STORE", f"{_tmp}/documents")
os.environ.setdefault("MIMIRSYNTH_DOC_ROOTS_BASE", f"{_tmp}/sources")
os.environ.setdefault("MIMIRSYNTH_SESSION_SECRET", "test-secret-not-for-production")
