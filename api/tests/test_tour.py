"""The guided tour of the interface (#364): whether a person has seen it lives on the server, per person, so it follows them across devices."""
from test_control import client  # noqa: F401  (fixture with the app and the test database)
from test_digest import _signed_in

from mimirsynth.deps import current_user
from mimirsynth.main import app
from mimirsynth.models import User
from mimirsynth.store import _factory


def _person(email: str, **kw) -> int:
    with _factory()() as db:
        u = User(email=email, name=email.split("@")[0], status="active", **kw)
        db.add(u)
        db.commit()
        return u.id


def test_the_tour_shows_until_it_is_finished_or_skipped_and_only_for_that_person(client):  # noqa: F811
    ana, bea = _person("ana-tour@example.com"), _person("bea-tour@example.com")
    try:
        app.dependency_overrides[current_user] = _signed_in(ana)
        assert client.get("/api/me").json()["tour_seen"] is False                     # first visit: the tour shows
        assert client.post("/api/me/tour", json={}).json() == {"tour_seen": True}     # skipped (or finished): seen
        assert client.get("/api/me").json()["tour_seen"] is True                      # not shown again, on any device
        assert client.post("/api/me/tour", json={"seen": True}).status_code == 200    # a replay from the help menu ends the same way
        assert client.get("/api/me").json()["tour_seen"] is True
        app.dependency_overrides[current_user] = _signed_in(bea)
        assert client.get("/api/me").json()["tour_seen"] is False                     # another person still gets it
        app.dependency_overrides[current_user] = _signed_in(ana)
        assert client.post("/api/me/tour", json={"seen": False}).json() == {"tour_seen": False}
        assert client.get("/api/me").json()["tour_seen"] is False                     # shown again on the next visit
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_the_tour_needs_a_session(client):  # noqa: F811
    from fastapi.testclient import TestClient
    from mimirsynth import ratelimit
    from mimirsynth.config import settings
    old = settings.auth_mode
    settings.auth_mode = "local"
    ratelimit.reset()
    try:
        assert TestClient(app).post("/api/me/tour", json={}).status_code == 401
    finally:
        settings.auth_mode = old


def test_people_who_signed_in_before_the_tour_existed_are_not_shown_it(tmp_path, monkeypatch):
    """The migration marks the tour seen for whoever had already signed in: they know the interface and can replay it from the help menu."""
    from datetime import datetime, timezone
    from pathlib import Path

    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config

    from mimirsynth import store
    eng = sa.create_engine(f"sqlite:///{tmp_path}/tour.db")
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(store.__file__).parent / "migrations"))
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0054")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(sa.text("INSERT INTO users (email, name, is_admin, created_at, last_login, display_name, picture_url, avatar_ref, session_epoch,"
                             " password_hash, status, must_change_password, failed_attempts, totp_secret, totp_enabled, locale, totp_last_step,"
                             " digest_hour, digest_weekday, timezone, digest_failures)"
                             " VALUES (:e, 'x', 0, :n, :l, '', '', '', 0, '', 'active', 0, 0, '', 0, '', 0, 8, 0, '', 0)"),
                     [{"e": "old@example.com", "n": now, "l": now}, {"e": "invited@example.com", "n": now, "l": None}])
        command.upgrade(cfg, "0056")
        seen = dict(conn.execute(sa.text("SELECT email, tour_seen_at IS NOT NULL FROM users")).all())
    assert seen == {"old@example.com": 1, "invited@example.com": 0}
