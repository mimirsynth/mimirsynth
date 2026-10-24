"""Identidad fija de la aplicación: el nombre y los enlaces oficiales no se configuran (ni por entorno ni por interfaz)."""
NAME = "MimirSynth"
REPO_URL = "https://github.com/MimirSynth/mimirsynth"
DOCS_URL = REPO_URL + "/tree/main/docs"
FEEDBACK_URL = REPO_URL + "/issues"
PUBLISHED = True


def links() -> dict:
    return {"docs": DOCS_URL, "repo": REPO_URL, "feedback": FEEDBACK_URL} if PUBLISHED else {"docs": "", "repo": "", "feedback": ""}
