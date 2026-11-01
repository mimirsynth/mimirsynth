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
