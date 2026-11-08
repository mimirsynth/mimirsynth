"""Identidad fija de la aplicación: el nombre y los enlaces oficiales no se configuran (ni por entorno ni por interfaz)."""
NAME = "MimirSynth"
REPO_URL = "https://github.com/MimirSynth/mimirsynth"
DOCS_URL = REPO_URL + "/tree/main/docs"
FEEDBACK_URL = REPO_URL + "/issues"
WIKI_URL = REPO_URL + "/wiki"  # the user guide (docs/wiki), linked from the screens that a page of it explains
PUBLISHED = True


def links() -> dict:
    return ({"docs": DOCS_URL, "repo": REPO_URL, "feedback": FEEDBACK_URL, "wiki": WIKI_URL} if PUBLISHED
            else {"docs": "", "repo": "", "feedback": "", "wiki": ""})
