"""#429: after an upgrade the browser must not reuse its old index.html, which points to hashed chunks the new image no longer has.
index.html (at / and on every SPA route that falls back to it) goes out with `Cache-Control: no-cache`; the hashed files under /assets
keep a long, immutable cache; the files of web/public/, at the root and without a hash, get neither."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mimirsynth.main import IMMUTABLE, mount_spa

INDEX = '<!doctype html><script type="module" src="/assets/index-AbC123.js"></script>'


@pytest.fixture
def spa(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    (tmp_path / "assets" / "index-AbC123.js").write_text("export {}", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    app = FastAPI()
    mount_spa(app, tmp_path)
    return TestClient(app)


@pytest.mark.parametrize("path", ["/", "/propuestas", "/entidad/1234", "/index.html"])
def test_index_html_is_always_revalidated(spa, path):
    r = spa.get(path)
    assert r.status_code == 200 and r.text == INDEX
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers.get("etag")  # what makes the revalidation cheap


def test_index_html_revalidates_to_a_304(spa):
    etag = spa.get("/").headers["etag"]
    r = spa.get("/propuestas", headers={"If-None-Match": etag})
    assert r.status_code == 304 and r.headers["cache-control"] == "no-cache"


def test_hashed_assets_are_cached_for_a_year(spa):
    r = spa.get("/assets/index-AbC123.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == IMMUTABLE == "public, max-age=31536000, immutable"
    r = spa.get("/assets/index-AbC123.js", headers={"If-None-Match": r.headers["etag"]})
    assert r.status_code == 304 and r.headers["cache-control"] == IMMUTABLE


def test_a_missing_chunk_is_a_404_not_the_index(spa):
    """An old index.html asking for a chunk of the previous version gets a 404, never index.html served as JavaScript."""
    r = spa.get("/assets/Overview-Old999.js")
    assert r.status_code == 404
    assert "cache-control" not in r.headers


def test_unhashed_files_at_the_root_keep_no_long_cache(spa):
    r = spa.get("/favicon.svg")
    assert r.status_code == 200
    assert "immutable" not in r.headers.get("cache-control", "")


@pytest.fixture
def nested_spa(tmp_path):
    """The build in a folder of its own, with a file next to it that is not part of the build."""
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text(INDEX, encoding="utf-8")
    (web / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("not part of the build", encoding="utf-8")
    app = FastAPI()
    mount_spa(app, web)
    return TestClient(app), tmp_path / "outside.txt"


@pytest.mark.parametrize("path", ["/%2e%2e/outside.txt", "/%2E%2E/outside.txt", "/assets/%2e%2e/%2e%2e/outside.txt",
                                  "/favicon.svg/%2e%2e/%2e%2e/outside.txt"])
def test_the_fallback_serves_only_files_of_the_build(nested_spa, path):
    client, _ = nested_spa
    r = client.get(path)
    assert "not part of the build" not in r.text
    assert r.status_code in (200, 404) and (r.status_code == 404 or r.text == INDEX)


def test_an_absolute_path_is_not_served(nested_spa):
    client, outside = nested_spa
    r = client.get("/" + outside.as_posix())
    assert "not part of the build" not in r.text


def test_files_of_the_build_are_still_served(nested_spa):
    client, _ = nested_spa
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/propuestas").text == INDEX
