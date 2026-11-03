"""The repository's own tooling (#168): one Alembic head, the changelog read from pull requests, and the wiki navigation in sync."""
import importlib.util
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_migrations_have_a_single_head():
    """Two pull requests that each add a migration on the same parent leave two heads: the second to merge must renumber."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "api" / "mimirsynth" / "migrations"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, f"several Alembic heads {heads}: make the newest migration revise the latest one"


BODY = """## What changes and why
Something.

## Changelog
<!-- One entry per line: Added, Changed, Deprecated, Removed, Fixed or Security, a colon and the text. -->
Added: **Incoming webhooks** (#122). Alerts become
memory, grouped.
- fixed: The recall no longer repeats a passage.

## Checklist
- [x] Tests
"""


def test_a_pull_request_body_gives_its_changelog_entries():
    cl = _script("changelog")
    assert cl.entries(BODY) == [("Added", "**Incoming webhooks** (#122). Alerts become memory, grouped."),
                                ("Fixed", "The recall no longer repeats a passage.")]
    assert cl.check({"body": BODY, "labels": []}) == ""
    assert "no «## Changelog» section" in cl.check({"body": "## What changes and why\nx", "labels": []})
    assert "has no entry" in cl.check({"body": "## Changelog\n<!-- Added: example -->\n", "labels": []})   # the template's comment is not an entry
    assert cl.check({"body": "", "labels": [{"name": "no-changelog"}]}) == ""                         # exempt by label
    assert cl.check({"body": "", "labels": [], "user": {"login": "dependabot[bot]"}}) == ""          # and dependency bumps


def test_entries_go_under_unreleased_in_order_and_once():
    cl = _script("changelog")
    text = ("# Changelog\n\nIntro.\n\n## [Unreleased]\n### Fixed\n- An old fix (#9)\n\n"
            "## [0.10.0] - 2026-11-01\n### Added\n- Something (#1)\n")
    new = {"Added": [cl.line(170, "**Webhooks** (#122). Text.")], "Fixed": [cl.line(171, "A fix (#171)."), "- An old fix (#9)"]}
    out = cl.merge(text, new)
    assert cl.unreleased(out) == ("## [Unreleased]\n### Added\n- **Webhooks** (#122). Text. (#170)\n\n"
                                  "### Fixed\n- An old fix (#9)\n- A fix (#171).\n\n")
    assert out.endswith("## [0.10.0] - 2026-11-01\n### Added\n- Something (#1)\n")
    rel = cl.merge(text, new, release="0.11.0", today=date(2026, 11, 20))
    assert "## [Unreleased]\n\n## [0.11.0] - 2026-11-20\n### Added\n- **Webhooks**" in rel and rel.count("## [0.10.0]") == 1
    prs = [{"number": 170, "title": "feat: webhooks", "body": "## Changelog\nAdded: **Webhooks** (#122). Text.", "labels": []},
           {"number": 172, "title": "chore: ci", "body": "", "labels": [{"name": "no-changelog"}]},
           {"number": 173, "title": "feat: forgot", "body": "## What", "labels": []}]
    lines, missing = cl.collect(prs)
    assert lines == {"Added": ["- **Webhooks** (#122). Text. (#170)"]} and missing == ["#173 feat: forgot"]


def test_the_wiki_navigation_is_generated_and_complete():
    """_Sidebar.md and the lists of Home.md and Inicio.md match _index.yml, and every page is in it. Fix: python scripts/wiki_index.py"""
    wi = _script("wiki_index")
    assert wi.main(["--check"]) == 0


def test_the_wiki_reference_tables_are_generated_from_the_code():
    """Notifications and Settings reference match notify.EVENTS / EVENT_DOCS and appsettings.REGISTRY (#184). Fix: python scripts/wiki_reference.py"""
    assert _script("wiki_reference").main(["--check"]) == 0


def test_the_wiki_reference_writer(tmp_path, monkeypatch, capsys):
    from mimirsynth.appsettings import Def
    wr = _script("wiki_reference")
    w = wr.Writer({"Se cayó": "It fell", "Cuándo cae": "When it falls", "Corte": "Outage", "Tamaño": "Size", "Cuánto": "How much", "MB": "MB"},
                  lambda page: {"Outage page": "Página de cortes"}[page])
    events = {"svc.down": ("critical", "Se cayó"), "svc.slow": ("info", "Lento")}
    docs = {"svc.down": ("Cuándo cae", "Outage page")}
    assert wr.notifications(events, docs, "en", w) == "| Event | Severity | When |\n|---|---|---|\n| `svc.down` | critical | When it falls ([[Outage page]]) |"
    assert wr.notifications(events, docs, "es", w).endswith("| `svc.down` | crítico | Cuándo cae ([[Página de cortes]]) |")
    assert "the event svc.slow has no description for the wiki (notify.EVENT_DOCS)" in w.problems
    reg = [Def("size_mb", "g", "Tamaño", "Cuánto", "float", "MB", 0.5, 10), Def("bare", "g", "Corte", "", "str")]
    table = wr.settings(reg, {"g": "Corte"}, {"size_mb": 2.5, "bare": ""}, "es", w)
    assert "| Tamaño | `size_mb` | `2,5` MB | 0,5–10 MB | Cuánto |" in table and "| Corte | `bare` | — | texto |  |" in table
    assert "the setting bare has no description (appsettings.REGISTRY)" in w.problems
    wr.settings([Def("x", "g", "Sin traducir", "Ayuda", "int")], {"g": "Corte"}, {"x": 1}, "en", w)
    assert any("no English translation" in p and "Sin traducir" in p for p in w.problems)

    # a page whose generated part was edited by hand is out of date: --check fails, and writing puts it back
    for name in ("Notifications.md", "Notificaciones.md", "Settings-reference.md", "Referencia-de-ajustes.md"):
        (tmp_path / name).write_bytes((wr.WIKI / name).read_bytes())
    page = tmp_path / "Notifications.md"
    good = page.read_bytes()
    page.write_bytes(good.replace(b"`graph.down` | critical", b"`graph.down` | info"))
    monkeypatch.setattr(wr, "WIKI", tmp_path)
    assert wr.main(["--check"]) == 1 and "Out of date: Notifications.md" in capsys.readouterr().out
    assert wr.main([]) == 0 and page.read_bytes() == good
    page.write_bytes(good.replace(b"<!-- generated:end -->", b""))
    try:
        wr.main(["--check"])
        raise AssertionError("a page without its end marker must be refused")
    except SystemExit as e:
        assert "generated markers" in str(e)
