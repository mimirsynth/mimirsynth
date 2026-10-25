"""Paquetes de ontología estándar: integridad de cada paquete, versionado y actualización sin perder cambios a mano."""
import re

import pytest

from test_control import client  # noqa: F401

from mimirsynth import ontology as ont

PACKS = ont.presets()
NAME = ont.NAME


def test_expected_packs_exist():
    assert set(PACKS) == {"general", "infrastructure", "team-projects", "personal-family", "software-knowledge"}


@pytest.mark.parametrize("name", sorted(PACKS))
def test_pack_integrity(name):
    p = PACKS[name]
    assert isinstance(p["version"], int) and p["version"] >= 1 and p["title"] and len(p["description"]) > 40 and p["standards"]
    o = ont.OntologyIn(**{k: p[k] for k in ("entity_types", "edge_types", "edge_type_map", "instructions")})
    ont.validate_ontology(o)  # los tipos del mapa existen, sin nombres repetidos
    ents, edges = [t["name"] for t in p["entity_types"]], [t["name"] for t in p["edge_types"]]
    assert all(NAME.match(n) for n in ents + edges)
    assert len(p["instructions"]) <= 4000 and "Use only the listed relation types" in p["instructions"]
    # sin tipos huérfanos: cada tipo de entidad y de relación (salvo RelatesTo, el último recurso) se usa en el mapa
    used_ents = {m["source"] for m in p["edge_type_map"]} | {m["target"] for m in p["edge_type_map"]}
    assert [e for e in ents if e not in used_ents] == [], "tipos de entidad que no aparecen en ninguna regla del mapa"
    used_edges = {e for m in p["edge_type_map"] for e in m["edge_types"]}
    assert [e for e in edges if e not in used_edges] == [], "tipos de relación que no aparecen en ninguna regla del mapa"
    assert "RelatesTo" in edges and "LAST RESORT" in next(t for t in p["edge_types"] if t["name"] == "RelatesTo")["description"]
    assert len({(m["source"], m["target"]) for m in p["edge_type_map"]}) == len(p["edge_type_map"]), "reglas del mapa repetidas"
    for m in p["edge_type_map"]:
        assert m["edge_types"] and len(set(m["edge_types"])) == len(m["edge_types"])


@pytest.mark.parametrize("name", sorted(PACKS))
def test_entity_descriptions_say_what_it_is_and_what_it_is_not(name):
    """Cada tipo principal dice qué es y cuándo sí / cuándo no, con ejemplos (el modelo clasifica solo con esta descripción)."""
    for t in PACKS[name]["entity_types"]:
        assert 25 <= len(t["description"]) <= 700, t["name"]
        assert not re.search(r"\b(TODO|lorem)\b", t["description"], re.I)
    rich = [t for t in PACKS[name]["entity_types"] if "Not for" in t["description"] and "Example" in t["description"]]
    assert len(rich) >= len(PACKS[name]["entity_types"]) // 2, "al menos la mitad de los tipos explican cuándo no usarlos y dan ejemplos"


def test_packs_are_in_english_and_no_personal_data():
    blob = " ".join(str(v) for p in PACKS.values() for v in (p["description"], p["instructions"], *[t["description"] for t in p["entity_types"] + p["edge_types"]]))
    assert not re.search(r"rafapuerta|10\.0\.\d+\.\d+|@gmail|seismenos", blob, re.I)


def test_generic_is_an_alias_of_general(client):  # noqa: F811
    client.post("/api/brains", json={"slug": "al", "name": "Al"})
    assert client.post("/api/brains/al/ontology/preset/generic").status_code == 200
    got = client.get("/api/brains/al/ontology").json()
    assert got["ontology"]["preset"] == {"name": "general", "version": PACKS["general"]["version"]}
    assert {i["name"] for i in got["presets_info"]} == set(PACKS) and got["preset_update"] is None


def test_update_by_merge_keeps_hand_edits(client, monkeypatch):  # noqa: F811
    client.post("/api/brains", json={"slug": "up", "name": "Up"})
    client.post("/api/brains/up/ontology/preset/general")
    # cambios a mano: descripción propia, un tipo propio y una regla propia
    o = client.get("/api/brains/up/ontology").json()["ontology"]
    next(t for t in o["entity_types"] if t["name"] == "Person")["description"] = "MI definición de persona"
    o["entity_types"].append({"name": "Pet", "description": "Mi mascota"})
    o["edge_type_map"].append({"source": "Pet", "target": "Person", "edge_types": ["Owns"]})
    o["instructions"] = "mis instrucciones"
    assert client.put("/api/brains/up/ontology", json=o).status_code == 200
    assert client.get("/api/brains/up/ontology").json()["ontology"]["preset"]["name"] == "general"  # editar a mano no pierde el origen
    # sale una versión nueva del paquete con un tipo nuevo, una relación nueva y una regla nueva
    new = {**PACKS["general"], "version": PACKS["general"]["version"] + 1,
           "entity_types": PACKS["general"]["entity_types"] + [{"name": "Product", "description": "A thing for sale. Not for: services. Example: 'Kettle'."}],
           "edge_types": PACKS["general"]["edge_types"] + [{"name": "Sells", "description": "An organization sells a product."}],
           "edge_type_map": PACKS["general"]["edge_type_map"] + [{"source": "Organization", "target": "Product", "edge_types": ["Sells"]}]}
    monkeypatch.setattr(ont, "presets", lambda: {**PACKS, "general": new})
    upd = client.get("/api/brains/up/ontology").json()["preset_update"]
    assert upd == {"name": "general", "installed": PACKS["general"]["version"], "available": new["version"]}
    assert client.post("/api/brains/up/ontology/preset/general?mode=nope").status_code == 422
    assert client.post("/api/brains/up/ontology/preset/general?mode=merge").status_code == 200
    got = client.get("/api/brains/up/ontology").json()
    o = got["ontology"]
    assert next(t for t in o["entity_types"] if t["name"] == "Person")["description"] == "MI definición de persona"  # lo hecho a mano se conserva
    assert {"Pet", "Product"} <= {t["name"] for t in o["entity_types"]} and "Sells" in {t["name"] for t in o["edge_types"]}
    assert any(m["source"] == "Pet" for m in o["edge_type_map"]) and any(m["target"] == "Product" for m in o["edge_type_map"])
    assert o["instructions"] == "mis instrucciones" and got["preset_update"] is None and o["preset"]["version"] == new["version"]
    # sustituir, en cambio, sí deja el paquete limpio
    assert client.post("/api/brains/up/ontology/preset/general?mode=replace").status_code == 200
    assert "Pet" not in {t["name"] for t in client.get("/api/brains/up/ontology").json()["ontology"]["entity_types"]}
