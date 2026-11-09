"""Identidad fija de la aplicación: el nombre y los enlaces oficiales no se configuran (ni por entorno ni por interfaz)."""
NAME = "MimirSynth"
REPO_URL = "https://github.com/MimirSynth/mimirsynth"
DOCS_URL = REPO_URL + "/tree/main/docs"
FEEDBACK_URL = REPO_URL + "/issues/new/choose"  # the issue templates: bug, beta feedback, installer, agent integration
WIKI_URL = REPO_URL + "/wiki"  # the user guide (docs/wiki), linked from the screens that a page of it explains
PUBLISHED = True
# Release stage, shown beside the version in the interface and at the top of the release notes. "beta" while versions stay 0.x
# (the API and the schema may change between minor versions); empty once 1.0 is out.
STAGE = "beta"


def links() -> dict:
    return ({"docs": DOCS_URL, "repo": REPO_URL, "feedback": FEEDBACK_URL, "wiki": WIKI_URL} if PUBLISHED
            else {"docs": "", "repo": "", "feedback": "", "wiki": ""})
