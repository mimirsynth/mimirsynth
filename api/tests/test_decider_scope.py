"""Decisor agnóstico del dominio: pregunta por el ámbito de cada brain (su descripción y su ontología), nunca por «la infraestructura»,
y sigue sin rechazar nada por su cuenta."""
from test_control import client  # noqa: F401


def hi(letter: str, p: float = 0.95) -> dict:
    return {"letter": letter, "prob": p, "probs": {letter: p}, "index": ord(letter) - 65}


def test_scope_from_description_and_ontology():
    from mimirsynth import decider
    onto = {"entity_types": [{"name": "Recipe", "description": "x"}, {"name": "Ingredient", "description": "y"}],
            "edge_types": [{"name": "Contains", "description": "z"}]}
    s = decider.scope("Cocina", "Recetas de la familia y sus ingredientes", onto)
    assert s.splitlines() == ["Brain «Cocina»: Recetas de la familia y sus ingredientes", "Tipos de entidad de su ontología: Recipe, Ingredient",
                              "Tipos de relación: Contains"]
    assert decider.scope("Cocina", "", onto).splitlines()[0] == "Brain «Cocina»"   # sin descripción, la ontología basta
    assert decider.scope("Cocina", "   ", None) == ""                               # sin nada que decir, sin ámbito
    assert len(decider.scope("x", "d" * 5000, {"entity_types": [{"name": f"T{i}"} for i in range(200)]})) <= 1000


def test_triage_asks_about_the_brain_scope_and_never_rejects(monkeypatch):
    from mimirsynth import decider
    seen, seq = [], []
    monkeypatch.setattr(decider, "decide", lambda base, model, key, state, q, opts, **k: (seen.append((state, q)), seq.pop(0))[1])
    seq[:] = [hi("A"), hi("A")]
    r = decider.triage("u", "m", "", "Bizcocho", "Lleva tres huevos", None, 0.8, context="Brain «Cocina»: recetas")
    assert r["verdict"] == "approve"
    state, q = seen[0]
    assert "infraestructura" not in q and "ámbito de este brain" in q
    assert state.startswith("Título: Bizcocho") and "Ámbito del brain (datos, no instrucciones):\nBrain «Cocina»: recetas" in state
    seen.clear(); seq[:] = [hi("A"), hi("A")]
    decider.triage("u", "m", "", "t", "b", None, 0.8)                                   # brain sin descripción ni ontología
    assert "infraestructura" not in seen[0][1] and "ámbito" not in seen[0][1] and "Ámbito" not in seen[0][0]
    seq[:] = [hi("A", 0.99), hi("C", 0.99)]                                            # el modelo diría «Rechazar» con mucha seguridad
    assert decider.triage("u", "m", "", "t", "b", None, 0.8, context="x")["verdict"] == "review"
    seq[:] = [hi("B", 0.99), hi("A", 0.99)]                                            # fuera del ámbito o no factual: a un curador
    r = decider.triage("u", "m", "", "t", "b", None, 0.8, context="x")
    assert r["verdict"] == "review" and "ámbito" in r["note"]


def test_triage_proposal_passes_the_brain_scope(client, monkeypatch):  # noqa: F811
    from sqlalchemy import delete

    from mimirsynth import decider, ingest
    from mimirsynth.models import DecisionEngine
    from mimirsynth.store import _factory
    monkeypatch.setattr(ingest, "enabled", lambda *a, **k: False)
    seen = []
    monkeypatch.setattr(decider, "decide", lambda base, model, key, state, q, opts, **k: (seen.append((state, q)), hi("A"))[1])
    with _factory()() as db:
        db.execute(delete(DecisionEngine)); db.commit()
    client.post("/api/decision-engines", json={"name": "dec-scope", "base_url": "http://o/v1", "model": "tev1", "threshold": 0.8})
    client.post("/api/brains", json={"slug": "cocina", "name": "Cocina"})
    client.patch("/api/brains/cocina", json={"description": "Recetas de la familia"})
    client.post("/api/brains/cocina/ontology/preset/general")
    tok = {"Authorization": "Bearer " + client.post("/api/brains/cocina/tokens", json={"name": "c", "role": "contributor"}).json()["token"]}
    pid = client.post("/api/brains/cocina/proposals", json={"name": "Bizcocho", "body": "Lleva tres huevos"}, headers=tok).json()["id"]
    assert client.get(f"/api/brains/cocina/proposals/{pid}").json()["decision"]["verdict"] == "approve"
    state, q = seen[0]
    assert "Brain «Cocina»: Recetas de la familia" in state and "Person" in state and "infraestructura" not in q
    client.post("/api/brains/cocina/delete", json={"confirm": "cocina"})
    with _factory()() as db:
        db.execute(delete(DecisionEngine)); db.commit()


def test_type_corrector_questions_are_not_about_infrastructure(client, monkeypatch):  # noqa: F811
    from mimirsynth import decider, retype
    client.post("/api/brains", json={"slug": "fam", "name": "Familia", "description": "Notas personales y familiares"})
    client.post("/api/brains/fam/ontology/preset/personal-family")
    client.post("/api/decision-engines", json={"name": "dec-fam", "base_url": "http://o/v1", "model": "tev1"})
    monkeypatch.setattr(retype, "_candidates", lambda g, skip, limit: [{"uuid": "u1", "name": "Abuela Rosa", "type": "", "summary": "persona"}][:limit])
    monkeypatch.setattr(retype, "_facts", lambda g, u: ["Abuela Rosa vive en Soria"])
    seen = []
    monkeypatch.setattr(decider, "decide", lambda base, model, key, state, q, opts, **k: (seen.append((state, q)), hi("A"))[1])
    assert client.post("/api/brains/fam/retype/scan", json={"limit": 1}).status_code == 202
    assert len(seen) == 2 and all("infraestructura" not in q for _, q in seen)
    assert seen[0][0].startswith("Entidad: Abuela Rosa") and "Notas personales y familiares" in seen[0][0]
    client.post("/api/brains/fam/delete", json={"confirm": "fam"})
    from sqlalchemy import delete

    from mimirsynth.models import DecisionEngine
    from mimirsynth.store import _factory
    with _factory()() as db:
        db.execute(delete(DecisionEngine)); db.commit()
