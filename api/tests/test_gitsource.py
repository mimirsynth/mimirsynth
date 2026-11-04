"""Git repositories as a document source (#118): choosing the files, the safety of the git calls, and a whole sync lifecycle against a
local repository served over file:// (allowed only here)."""
import os
import subprocess
from pathlib import Path

import pytest

from test_control import _as, client  # noqa: F401
from test_docs import MD, fake_index  # noqa: F401
from test_docsources import _brain, _docs

from mimirsynth import gitsource
from mimirsynth.main import app
from mimirsynth.models import DocSource
from mimirsynth.store import _factory

ENV = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")}, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
       "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.com"}


def _run(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, env=ENV, check=True, capture_output=True, text=True).stdout


def _write(repo: Path, files: dict[str, str | None]) -> None:
    for path, text in files.items():
        p = repo / path
        if text is None:
            p.unlink()
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="")


def _commit(repo: Path, files: dict[str, str | None], msg: str) -> str:
    _write(repo, files)
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", msg)
    return _run(repo, "rev-parse", "HEAD").strip()


@pytest.fixture()
def origin(tmp_path, monkeypatch):
    """A repository with documents, code and things that must stay out, served to the instance over file:// for the test."""
    monkeypatch.setattr(gitsource, "PROTOCOLS", ("https", "http", "file"))
    repo = tmp_path / "origin"
    repo.mkdir()
    _run(repo, "init", "-q", "-b", "main")
    for k, v in (("core.autocrlf", "false"), ("uploadpack.allowFilter", "true"), ("uploadpack.allowAnySHA1InWant", "true")):
        _run(repo, "config", k, v)
    _commit(repo, {"README.md": "# Proyecto\n\nQué es y cómo se instala.\n", "docs/a.md": MD, "docs/adr/0001-base.md": "# ADR 1\n\nUsamos FalkorDB.\n",
                   "docs/.env.md": "TOKEN=xyz\n", "docs/keys/id_rsa.txt": "-----BEGIN-----\n", "src/app.py": "print('code')\n",
                   "notes/other.md": "# Fuera de las rutas\n"}, "uno")
    return repo


def test_choosing_files_by_path():
    inc = gitsource.DEFAULT_INCLUDE
    assert gitsource.included("README.md", inc) and gitsource.included("readme.rst", inc) and gitsource.included("CHANGELOG.md", inc)
    assert not gitsource.included("pkg/README.md", inc)                           # a pattern without a folder is at the root only
    assert gitsource.included("docs/a/b/c.md", inc) and gitsource.included("services/api/adr/0002.md", inc) and gitsource.included("adr/1.md", inc)
    assert not gitsource.included("documentation/x.md", inc)
    for p in ("docs/.env.md", "docs/.hidden/x.md", "docs/keys/id_rsa.txt", "docs/server.pem", "docs/credentials.txt", "docs/x.tfstate.md"):
        assert gitsource.excluded(p), p
    assert not gitsource.excluded("docs/secret-management.md")                    # a document about secrets is a document
    assert gitsource.included("docs/x/adr/y/z.md", ["docs/**/adr/**"]) and not gitsource.included("docs/x/adr", ["docs/**/adr/**"])
    assert gitsource.included("a/B/c.MD", ["a/?/*.md"]) and not gitsource.included("a/bb/c.md", ["a/?/*.md"])
    assert gitsource.check_include(["docs//**/**/x", "docs/**"]) == ["docs/**/x", "docs/**"]

    entries = [("100644", "b1", "docs/a.md"), ("120000", "b2", "docs/link.md"), ("160000", "b3", "docs/sub"), ("100755", "b4", "docs/run.txt"),
               ("100644", "b5", "docs/app.py"), ("100644", "b6", "docs/.env.md")]
    assert gitsource.select(entries, inc) == {"docs/a.md": "b1", "docs/run.txt": "b4"}   # no links, no submodules, only document types


def test_a_pattern_cannot_stall_the_process():
    """Repeated `**` and `*` against a long path: a regex would backtrack for minutes (the reviewer's case took 0.84 s with four)."""
    import time
    evil = ["**a**a**a**ab", "**a" * 60 + "b", "**/a" * 50 + "/b", "*a" * 99 + "b", "/".join(["*a*a*a*a*a*a*a*a*a*b"] * 20)]
    paths = ["a" * 479, "/".join(["a" * 9] * 48), "a/" * 239 + "a"]
    t0 = time.monotonic()
    for p in evil:
        for path in paths:
            assert not gitsource.included(path, [p])
    assert time.monotonic() - t0 < 1.0


def test_what_the_administrator_gives_is_checked():
    assert gitsource.check_url(" https://git.example.com/team/repo.git ") == "https://git.example.com/team/repo.git"
    for bad in ("ftp://x/y", "ssh://git@x/y", "git@github.com:x/y.git", "ext::sh -c touch% /tmp/x", "file:///etc", "https://user:pw@x.com/r.git",
                "https://tok@x.com/r.git", "-u https://x.com/r", "https://x.com/a b"):
        with pytest.raises(ValueError):
            gitsource.check_url(bad)
    assert gitsource.check_branch("") == "" and gitsource.check_branch("release/1.2") == "release/1.2"
    for bad in ("-x", "a..b", "a b", "x/", "a//b", "--upload-pack=x"):
        with pytest.raises(ValueError):
            gitsource.check_branch(bad)
    assert gitsource.check_include(None) == gitsource.DEFAULT_INCLUDE and gitsource.check_include(["./docs/**", " ", "docs/**"]) == ["docs/**"]
    for bad in (["/etc/**"], ["../x"], ["docs/../../x"], [], [" "]):
        with pytest.raises(ValueError):
            gitsource.check_include(bad)


def test_links_to_the_forge():
    c, p = "abc123", "docs/adr/0001 base.md"
    assert gitsource.web_link("https://github.com/o/r.git", c, p) == "https://github.com/o/r/blob/abc123/docs/adr/0001%20base.md"
    assert gitsource.web_link("https://gitlab.example.com/g/sub/r.git", c, p).startswith("https://gitlab.example.com/g/sub/r/-/blob/abc123/")
    assert gitsource.web_link("https://bitbucket.org/o/r.git", c, p).startswith("https://bitbucket.org/o/r/src/abc123/")
    assert gitsource.web_link("https://codeberg.org/o/r", c, p).startswith("https://codeberg.org/o/r/src/commit/abc123/")
    assert gitsource.web_link("https://dev.azure.com/o/p/_git/r", c, p) is None
    assert gitsource.web_link("file:///srv/r", c, p) is None


def test_the_token_goes_in_a_header_and_never_in_the_command_line():
    env = gitsource._env("https://git.example.com/o/r.git", "tok-secreto", "bot")
    keys = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))}
    import base64
    assert keys["http.https://git.example.com/o/r.git.extraHeader"] == "Authorization: Basic " + base64.b64encode(b"bot:tok-secreto").decode()
    assert keys["protocol.allow"] == "never" and keys["credential.helper"] == "" and keys["core.symlinks"] == "false"
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_CONFIG_GLOBAL"] == os.devnull
    with pytest.raises(ValueError):
        gitsource._env("http://git.example.com/o/r.git", "tok")                   # never in clear text


def test_git_source_lifecycle(client, fake_index, origin):  # noqa: F811
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    url = origin.as_uri()
    assert client.post(f"{base}/sources/git", json={"name": "x", "url": url, "branch": "no-existe"}).json()["detail"].startswith("no se pudo conectar")
    assert client.post(f"{base}/sources/git", json={"name": "x", "url": "https://u:p@x.test/r.git"}).status_code == 400
    r = client.post(f"{base}/sources/git", json={"name": "x", "url": url, "branch": "-x"}, headers={"Accept-Language": "en"})
    assert r.status_code == 400 and r.json()["detail"] == "the branch name is not valid"            # validation messages are translated
    r = client.post(f"{base}/sources/git", json={"name": "Repo", "url": url, "sync_interval": 60})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    ds = _docs(client, slug)
    assert sorted(ds) == ["README.md", "docs/a.md", "docs/adr/0001-base.md"]       # no hidden, no keys, no code, nothing outside the paths
    assert all(d["status"] == "active" and d["chunks"] > 0 for d in ds.values())
    assert client.get(f"{base}/{ds['docs/a.md']['id']}/file").content == MD.encode()
    src = next(s for s in client.get(f"{base}/sources").json()["sources"] if s["id"] == sid)
    first = _run(origin, "rev-parse", "HEAD").strip()
    assert src["kind"] == "git" and src["config"]["commit"] == first and src["config"]["include"] == gitsource.DEFAULT_INCLUDE and src["config"]["secrets_set"] == []
    job = client.get(f"/api/brains/{slug}/jobs?kind=doc.scan").json()["items"][0]
    assert client.get(f"/api/brains/{slug}/jobs/{job['id']}").json()["result"] == {"added": 3, "changed": 0, "unchanged": 0, "removed": 0, "indexed": 3,
                                                                                  "errors": 0, "commit": first[:12]}
    # only the chosen files were downloaded: the code and the rest of the tree are not in the clone
    clone = gitsource.repo_dir(*_ids(sid))
    missing = _run(clone, "rev-list", "--objects", "--missing=print", first)
    assert _run(origin, "rev-parse", f"{first}:src/app.py").strip() in missing

    # a new commit: one file changed, one added, one gone; the unchanged one is not read again
    second = _commit(origin, {"docs/a.md": MD + "\nUna sección nueva.\n", "docs/b.md": "# B\n\nOtro documento.\n", "docs/adr/0001-base.md": None}, "dos")
    r = client.post(f"{base}/sources/{sid}/scan")
    res = client.get(f"/api/brains/{slug}/jobs/{r.json()['job']}").json()["result"]
    assert res == {"added": 1, "changed": 1, "unchanged": 1, "removed": 1, "indexed": 2, "errors": 0, "commit": second[:12]}
    ds = _docs(client, slug)
    assert sorted(ds) == ["README.md", "docs/a.md", "docs/b.md"]
    with _factory()() as db:
        from mimirsynth.models import Document
        a = db.get(Document, ds["docs/a.md"]["id"])
        assert a.meta["commit"] == second and a.meta["path"] == "docs/a.md" and db.get(Document, ds["README.md"]["id"]).meta["commit"] == first

    # a scheduled sync with no new commit reads nothing
    from mimirsynth import docsources
    with _factory()() as db:
        jid = docsources._submit_scan(db.get(DocSource, sid), None, manual=False)
    assert client.get(f"/api/brains/{slug}/jobs/{jid}").json()["result"] == {"added": 0, "changed": 0, "unchanged": 3, "removed": 0, "indexed": 0,
                                                                            "errors": 0, "commit": second[:12]}

    # if the repository cannot be reached, or the paths select too many files, nothing is deleted
    with _factory()() as db:
        s = db.get(DocSource, sid)
        s.config = {**s.config, "url": (origin.parent / "gone").as_uri()}
        db.commit()
    r = client.post(f"{base}/sources/{sid}/scan")
    assert client.get(f"/api/brains/{slug}/jobs/{r.json()['job']}").json()["status"] == "failed"
    src = next(s for s in client.get(f"{base}/sources").json()["sources"] if s["id"] == sid)
    assert src["status"] == "error" and "No se ha borrado nada" in src["last_error"] and len(_docs(client, slug)) == 3
    with _factory()() as db:
        s = db.get(DocSource, sid)
        s.config = {**s.config, "url": url}
        db.commit()
    gitsource_max = gitsource.MAX_FILES
    gitsource.MAX_FILES = 1
    try:
        r = client.post(f"{base}/sources/{sid}/scan")
        assert client.get(f"/api/brains/{slug}/jobs/{r.json()['job']}").json()["status"] == "failed" and len(_docs(client, slug)) == 3
    finally:
        gitsource.MAX_FILES = gitsource_max

    # narrowing the paths takes the rest out at the next sync, which the change starts
    r = client.patch(f"{base}/sources/{sid}", json={"include": ["README*"]})
    assert r.status_code == 200 and r.json()["job"]
    assert sorted(_docs(client, slug)) == ["README.md"]
    assert client.patch(f"{base}/sources/{sid}", json={"include": ["../x"]}).status_code == 400

    assert client.delete(f"{base}/sources/{sid}").json() == {"ok": True, "documents_removed": 1}
    assert not clone.exists()                                                     # the local clone goes with the source


def _ids(sid: int) -> tuple[int, int]:
    with _factory()() as db:
        s = db.get(DocSource, sid)
        return s.brain_id, s.id


def test_a_token_is_stored_sealed_and_never_shown(client, fake_index, origin, monkeypatch):  # noqa: F811
    seen = []
    real = gitsource._env
    monkeypatch.setattr(gitsource, "_env", lambda url, token="", username="": seen.append(token) or real(url))  # file:// cannot carry it
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    sid = client.post(f"{base}/sources/git", json={"name": "Privado", "url": origin.as_uri(), "token": "tok-de-prueba", "username": "bot"}).json()["id"]
    assert "tok-de-prueba" in seen
    assert "tok-de-prueba" not in client.get(f"{base}/sources").text
    src = next(s for s in client.get(f"{base}/sources").json()["sources"] if s["id"] == sid)
    assert src["config"]["secrets_set"] == ["token"] and src["config"]["settings"] == {"username": "bot"}
    with _factory()() as db:
        assert "tok-de-prueba" not in str(db.get(DocSource, sid).config)
    clone = gitsource.repo_dir(*_ids(sid))
    assert "tok-de-prueba" not in (clone / ".git" / "config").read_text()
    seen.clear()
    assert client.patch(f"{base}/sources/{sid}", json={"branch": "main"}).status_code == 200       # the stored token is kept
    assert "tok-de-prueba" in seen
    assert client.patch(f"{base}/sources/{sid}", json={"clear_token": True}).status_code == 200
    assert next(s for s in client.get(f"{base}/sources").json()["sources"] if s["id"] == sid)["config"]["secrets_set"] == []
    # connecting a repository makes the server reach an address: only the instance administrator does it
    assert client.put(f"/api/brains/{slug}/members", json={"email": "bea@x.com", "role": "admin"}).status_code == 200
    _as("bea@x.com", "Bea")
    try:
        assert client.post(f"{base}/sources/git", json={"name": "y", "url": origin.as_uri()}).status_code == 403
        assert client.patch(f"{base}/sources/{sid}", json={"include": ["docs/**"]}).status_code == 403
        assert client.patch(f"{base}/sources/{sid}", json={"name": "Renombrado"}).status_code == 200
    finally:
        app.dependency_overrides.clear()
