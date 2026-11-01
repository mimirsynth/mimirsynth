"""Incoming webhooks (#122): a wrong secret creates nothing, each template reads a real body of its emitter, an alert that fires ten
times and resolves leaves one proposal with its start and end, one that outlives the window leaves two, and the limits hold."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest

from test_control import client  # noqa: F401

ALERTMANAGER = {
    "version": "4", "groupKey": "{}:{alertname=\"HostDown\"}", "truncatedAlerts": 0, "status": "firing", "receiver": "mimirsynth",
    "groupLabels": {"alertname": "HostDown"}, "commonLabels": {"alertname": "HostDown", "instance": "nas01:9100", "job": "node", "severity": "critical"},
    "commonAnnotations": {"summary": "nas01 no responde"}, "externalURL": "http://alertmanager:9093",
    "alerts": [{"status": "firing", "labels": {"alertname": "HostDown", "instance": "nas01:9100", "job": "node", "severity": "critical"},
                "annotations": {"summary": "nas01 no responde", "description": "El exporter de nas01 lleva 5 minutos sin contestar."},
                "startsAt": "2026-10-30T10:00:00.123456789Z", "endsAt": "0001-01-01T00:00:00Z",
                "generatorURL": "http://prometheus:9090/graph?g0.expr=up%3D%3D0", "fingerprint": "5b3e1f0c7a9d2e41"}]}
CHECKMK = {"NOTIFY_WHAT": "SERVICE", "NOTIFY_NOTIFICATIONTYPE": "PROBLEM", "NOTIFY_HOSTNAME": "pve01", "NOTIFY_SERVICEDESC": "Filesystem /var",
           "NOTIFY_SERVICESTATE": "CRITICAL", "NOTIFY_SERVICEOUTPUT": "CRIT - 96.1% used (115 of 120 GiB)",
           "NOTIFY_LONGDATETIME": "Thu Oct 30 10:00:00 CET 2026", "NOTIFY_MICROTIME": "1793354400123456", "NOTIFY_CONTACTNAME": "mimirsynth"}
KUMA_DOWN = {"heartbeat": {"monitorID": 3, "status": 0, "time": "2026-10-30 10:00:00.123", "msg": "timeout of 48000ms exceeded", "important": True,
                           "duration": 0, "timezone": "UTC", "localDateTime": "2026-10-30 10:00:00"},
             "monitor": {"id": 3, "name": "Nextcloud", "type": "http", "url": "https://nube.example.org", "hostname": None},
             "msg": "[Nextcloud] [🔴 Down] timeout of 48000ms exceeded"}
PROXMOX = {"title": "vzdump backup status (pve01): backup failed", "message": "Details\n=======\nVMID 104 failed: unable to read tape",
           "severity": "error", "timestamp": 1793354400, "fields": {"hostname": "pve01", "type": "vzdump", "job-id": "backup-daily"}}
GITHUB_RUN = {"action": "completed", "workflow_run": {"id": 30433642, "name": "Deploy", "head_branch": "main", "head_sha": "acb5820ced9479c074f688cc328bf03f341a511d",
              "event": "push", "status": "completed", "conclusion": "success", "html_url": "https://github.com/acme/app/actions/runs/30433642",
              "run_started_at": "2026-10-30T09:58:00Z", "updated_at": "2026-10-30T10:02:00Z", "actor": {"login": "octocat"}},
              "repository": {"full_name": "acme/app"}, "sender": {"login": "octocat"}}
GITHUB_DEPLOY = {"action": "created", "deployment_status": {"state": "failure", "environment": "production", "description": "Health check failed",
                 "target_url": "https://ci.example.org/logs/42", "created_at": "2026-10-30T10:05:00Z", "updated_at": "2026-10-30T10:05:00Z",
                 "creator": {"login": "deploy-bot"}}, "deployment": {"ref": "v1.4.0", "sha": "9049f1265b7d61be4a8904a9a27120d2064dab3b",
                 "environment": "production"}, "repository": {"full_name": "acme/app"}}
GITLAB_PIPELINE = {"object_kind": "pipeline", "object_attributes": {"id": 31, "ref": "main", "tag": False, "sha": "bcbb5ec396a2c0f828686f14fac9b80b780504f2",
                   "source": "push", "status": "failed", "detailed_status": "failed", "created_at": "2026-10-30 09:50:00 UTC",
                   "finished_at": "2026-10-30 10:00:00 UTC", "duration": 600, "url": "https://gitlab.example.org/infra/ansible/-/pipelines/31"},
                   "user": {"username": "root"}, "project": {"path_with_namespace": "infra/ansible"}}
GITLAB_DEPLOY = {"object_kind": "deployment", "status": "success", "status_changed_at": "2026-10-30 10:10:00 +0100", "deployment_id": 15,
                 "deployable_url": "https://gitlab.example.org/infra/web/-/jobs/1", "environment": "production", "project": {"path_with_namespace": "infra/web"},
                 "short_sha": "279484c0", "user": {"username": "root"}, "ref": "main"}


def _sign(secret: str, body: bytes) -> dict:
    return {"X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), "Content-Type": "application/json"}


def _hook(client, slug, template="alertmanager", **kw):  # noqa: F811
    r = client.post(f"/api/brains/{slug}/webhooks", json={"name": f"{template} {slug}", "template": template, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _send(client, hook, payload, headers=None, raw=None):  # noqa: F811
    body = raw if raw is not None else json.dumps(payload).encode()
    return client.post(hook["path"], content=body, headers=headers if headers is not None else _sign(hook["secret"], body))


def _proposals(slug):
    """The proposals made by the webhooks of this brain (their source names the brain: rows left by other tests do not count)."""
    from mimirsynth.models import Brain, Proposal
    from mimirsynth.store import _factory
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == slug).one().id
        return [(p.name, p.body, p.status, p.source_description, p.reference_time) for p in db.query(Proposal).filter(
            Proposal.brain_id == bid, Proposal.source_description.like(f"webhook «% {slug}»%")).order_by(Proposal.id)]


@pytest.fixture(autouse=True)
def _fresh_limits():
    from mimirsynth import ratelimit
    ratelimit.reset()


@pytest.mark.parametrize("template,body,headers,expect", [
    ("alertmanager", ALERTMANAGER, {}, [("firing", "HostDown · nas01:9100", "2026-10-30T10:00:00.123456+00:00")]),
    ("checkmk", CHECKMK, {}, [("firing", "Filesystem /var · pve01", "2026-10-30T10:00:00.123456+00:00")]),
    ("uptime_kuma", KUMA_DOWN, {}, [("firing", "Nextcloud", "2026-10-30T10:00:00.123000+00:00")]),
    ("proxmox", PROXMOX, {}, [("event", "vzdump backup status (pve01): backup failed", "2026-10-30T10:00:00+00:00")]),
    ("github_actions", GITHUB_RUN, {"X-GitHub-Event": "workflow_run"}, [("event", "acme/app · Deploy · success", "2026-10-30T10:02:00+00:00")]),
    ("github_actions", GITHUB_DEPLOY, {"X-GitHub-Event": "deployment_status"}, [("event", "acme/app · deploy production · failure", "2026-10-30T10:05:00+00:00")]),
    ("github_actions", {"zen": "Keep it logically awesome.", "hook_id": 1}, {"X-GitHub-Event": "ping"}, []),
    ("gitlab_ci", GITLAB_PIPELINE, {}, [("event", "infra/ansible · pipeline main · failed", "2026-10-30T10:00:00+00:00")]),
    ("gitlab_ci", GITLAB_DEPLOY, {}, [("event", "infra/web · deploy production · success", "2026-10-30T10:10:00+01:00")]),
])
def test_each_template_reads_a_real_body(template, body, headers, expect):
    from mimirsynth import hooktemplates
    evs = hooktemplates.parse(template, body, headers)
    assert [(e.state, e.title, e.at.isoformat() if e.at else None) for e in evs] == expect
    if evs and template != "proxmox":
        assert evs[0].text                                                         # the emitter's own details travel with it
    resolved = {"alertmanager": {**ALERTMANAGER, "alerts": [{**ALERTMANAGER["alerts"][0], "status": "resolved", "endsAt": "2026-10-30T10:30:00Z"}]},
                "checkmk": {**CHECKMK, "NOTIFY_NOTIFICATIONTYPE": "RECOVERY", "NOTIFY_SERVICESTATE": "OK"},
                "uptime_kuma": {**KUMA_DOWN, "heartbeat": {**KUMA_DOWN["heartbeat"], "status": 1, "msg": "200 - OK"}}}.get(template)
    if resolved:
        again = hooktemplates.parse(template, resolved, headers)
        assert again[0].state == "resolved" and again[0].fingerprint == evs[0].fingerprint     # the same alert: it closes the group
    assert hooktemplates.parse("checkmk", {**CHECKMK, "NOTIFY_NOTIFICATIONTYPE": "ACKNOWLEDGEMENT"}) == []


def test_the_generic_template_maps_any_json():
    from mimirsynth import hooktemplates
    cfg = {"title": "{{check.name}} en {{check.host}}", "text": "{{check.output}}", "at": "time", "state": "check.status", "fingerprint": "check.id"}
    body = {"check": {"id": 7, "name": "disco", "host": "nas01", "output": "lleno", "status": "CRITICAL"}, "time": "2026-10-30T10:00:00Z"}
    [e] = hooktemplates.parse("generic", body, {}, cfg)
    assert (e.state, e.title, e.text, e.at.isoformat()) == ("firing", "disco en nas01", "lleno", "2026-10-30T10:00:00+00:00")
    assert hooktemplates.parse("generic", {**body, "check": {**body["check"], "status": "OK"}}, {}, cfg)[0].state == "resolved"
    assert hooktemplates.parse("generic", {"title": "Backup hecho"}, {}, {})[0].state == "event"


def test_a_wrong_secret_answers_401_and_creates_nothing(client):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "wh1", "name": "Wh1"}).status_code == 201
    hook = _hook(client, "wh1")
    body = json.dumps(ALERTMANAGER).encode()
    assert _send(client, hook, None, _sign("otro-secreto", body), body).status_code == 401
    assert _send(client, hook, None, {"Authorization": "Bearer nope"}, body).status_code == 401
    assert _send(client, hook, None, {}, body).status_code == 401                               # no credential at all
    assert client.post(hook["path"].replace("/wh1/", "/otro/"), content=body, headers=_sign(hook["secret"], body)).status_code == 401
    assert client.post(hook["path"][:-3] + "xyz", content=body, headers=_sign(hook["secret"], body)).status_code == 401
    assert client.get(f"/api/brains/wh1/webhooks/{hook['id']}/events").json() == [] and _proposals("wh1") == []
    listed = client.get("/api/brains/wh1/webhooks").json()["items"][0]
    assert listed["rejected"] >= 2 and "secret" not in listed
    # a token in a header works too, and disabling the webhook closes it
    assert _send(client, hook, ALERTMANAGER, {"Authorization": f"Bearer {hook['secret']}"}).status_code == 202
    assert _send(client, hook, ALERTMANAGER, {"X-Gitlab-Token": hook["secret"]}).status_code == 202
    client.put(f"/api/brains/wh1/webhooks/{hook['id']}", json={"name": "x", "template": "alertmanager", "enabled": False})
    assert _send(client, hook, ALERTMANAGER).status_code == 401
    rotated = client.post(f"/api/brains/wh1/webhooks/{hook['id']}/rotate").json()
    assert rotated["secret"] != hook["secret"]


def test_an_alert_that_fires_ten_times_and_resolves_is_one_proposal(client):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "wh2", "name": "Wh2"}).status_code == 201
    hook = _hook(client, "wh2")
    for _ in range(10):
        r = _send(client, hook, ALERTMANAGER)
        assert r.status_code == 202
    assert r.json()["outcomes"] == [{"title": "HostDown · nas01:9100", "outcome": "grouped", "count": 10}]
    assert _proposals("wh2") == []                                                              # nothing proposed while it fires
    done = {**ALERTMANAGER, "status": "resolved", "alerts": [{**ALERTMANAGER["alerts"][0], "status": "resolved", "endsAt": "2026-10-30T10:30:00Z"}]}
    assert _send(client, hook, done).status_code == 202
    [(name, body, status, origin, ref)] = _proposals("wh2")
    assert name == "HostDown · nas01:9100" and status == "pending" and origin.startswith("webhook «alertmanager wh2»")
    assert "2026-10-30 10:00 UTC" in body and "2026-10-30 10:30 UTC" in body and "10 avisos" in body and "nas01 no responde" in body
    [ev] = client.get(f"/api/brains/wh2/webhooks/{hook['id']}/events").json()
    assert (ev["kind"], ev["outcome"], ev["count"]) == ("alert", "closed", 10) and ev["resolved_at"]


def test_an_alert_that_outlives_the_window_is_proposed_firing_and_then_resolved(client, monkeypatch):  # noqa: F811
    from mimirsynth import webhooks
    from mimirsynth.models import WebhookEvent
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "wh3", "name": "Wh3"}).status_code == 201
    hook = _hook(client, "wh3", template="checkmk")
    for _ in range(3):
        _send(client, hook, CHECKMK)
    with _factory()() as db:
        g = db.query(WebhookEvent).filter(WebhookEvent.webhook_id == hook["id"]).one()
        g.created_at = datetime.now(timezone.utc) - timedelta(hours=2); db.commit()   # first received long ago
    webhooks.flush_due(); webhooks.flush_due()                  # (other tests may leave open alerts too)
    [(name, body, *_)] = _proposals("wh3")                         # proposed once
    assert "sin resolver" in body and "3 avisos" in body
    _send(client, hook, {**CHECKMK, "NOTIFY_NOTIFICATIONTYPE": "RECOVERY", "NOTIFY_SERVICESTATE": "OK"})
    second = _proposals("wh3")[1]
    assert "resuelto" in second[1].lower() and "3 avisos" in second[1]
    [ev] = client.get(f"/api/brains/wh3/webhooks/{hook['id']}/events").json()
    assert ev["proposal_id"] and ev["resolution_id"] and ev["outcome"] == "closed"


def test_limits_secrets_trusted_hooks_and_bad_bodies(client, monkeypatch):  # noqa: F811
    from mimirsynth import ingest, notify
    monkeypatch.setattr(ingest, "enabled", lambda: False)   # an approved proposal stays approved (no engine to ingest it here)
    emitted = []
    monkeypatch.setattr(notify, "emit", lambda *a, **k: emitted.append(a[0]))
    assert client.post("/api/brains", json={"slug": "wh4", "name": "Wh4"}).status_code == 201
    hook = _hook(client, "wh4", template="proxmox", daily_cap=2, per_minute=5, auto_approve=True)
    leak = {**PROXMOX, "message": "backup failed; retry with password=Sup3rS3cr3t!x and token ghp_" + "a" * 36}
    out = [_send(client, hook, leak).json()["outcomes"][0]["outcome"] for _ in range(3)]
    assert out == ["proposed", "proposed", "capped"] and "webhook.capped" in emitted                     # daily cap
    props = _proposals("wh4")
    assert len(props) == 2 and all("ghp_aaaa" not in b for _, b, *_ in props)   # through the secret detector: a sure token is masked
    assert all(status == "pending" for _, _, status, *_ in props)       # trusted, but something was flagged: a person looks at it
    clean = _hook(client, "wh4", template="proxmox", auto_approve=True)
    _send(client, clean, PROXMOX)
    assert _proposals("wh4")[-1][2] == "approved"                        # trusted and clean: approved directly
    codes = [_send(client, hook, PROXMOX).status_code for _ in range(4)]
    assert codes[-1] == 429                                              # requests per minute
    assert _send(client, clean, None, raw=b"not json").status_code == 400
    big = b'{"title": "' + b"x" * (256 * 1024) + b'"}'
    assert _send(client, clean, None, raw=big).status_code == 413


def test_admin_preview_and_permissions(client):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "wh5", "name": "Wh5"}).status_code == 201
    r = client.post("/api/brains/wh5/webhooks/preview", json={"template": "github_actions", "event": "workflow_run", "body": json.dumps(GITHUB_RUN)})
    assert r.status_code == 200 and r.json()["events"][0]["title"] == "acme/app · Deploy · success"
    assert client.post("/api/brains/wh5/webhooks/preview", json={"template": "generic", "body": "{nope"}).status_code == 400
    assert client.post("/api/brains/wh5/webhooks", json={"name": "x", "template": "nope"}).status_code == 422
    tok = client.post("/api/brains/wh5/tokens", json={"name": "c", "role": "curator"}).json()["token"]
    assert client.get("/api/brains/wh5/webhooks", headers={"Authorization": f"Bearer {tok}"}).status_code == 403
    hook = _hook(client, "wh5", template="generic", config={"title": "{{name}}", "evil": "x", "state": ""})
    assert hook["config"] == {"title": "{{name}}"}                     # only the known keys of the mapping are kept
    assert client.delete(f"/api/brains/wh5/webhooks/{hook['id']}").status_code == 204
    assert client.get("/api/brains/wh5/webhooks").json()["items"] == []
