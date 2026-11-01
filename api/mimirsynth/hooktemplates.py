"""Templates of the incoming webhooks (#122): each turns the JSON an emitter sends into events.

An event is either an **alert** (`firing` or `resolved`, with a `fingerprint` that identifies the same alert across repetitions) or a
one-off **event** (a deployment, a pipeline, a backup). Titles and texts keep the emitter's own words; the sentence around them, in the
instance's language, is written by `webhooks`. A body the template does not recognise, or that announces nothing final (a pipeline
still running, a ping), gives no events.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Event:
    state: str                 # firing | resolved | event
    title: str
    text: str = ""
    at: datetime | None = None
    fingerprint: str = ""
    details: dict = field(default_factory=dict)

    def out(self) -> dict:
        return {"state": self.state, "title": self.title, "text": self.text, "at": self.at.isoformat() if self.at else None,
                "fingerprint": self.fingerprint}


def ts(v) -> datetime | None:
    """A date as emitters write it: ISO 8601, «2026-10-30 10:00:00 UTC», epoch seconds or microseconds. None when unknown or a
    placeholder (Alertmanager's 0001-01-01 for «not yet»)."""
    if v in (None, "", 0):
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r"\d{9,17}(\.\d+)?", v.strip())):
        n = float(v)
        if n > 1e14:      # microseconds (CheckMK's MICROTIME)
            n /= 1e6
        elif n > 1e11:    # milliseconds
            n /= 1e3
        return datetime.fromtimestamp(n, timezone.utc)
    s = re.sub(r"\s*UTC$", "+00:00", str(v).strip())
    s = re.sub(r"\s([+-]\d{2}):?(\d{2})$", r"\1:\2", s)   # «… +0000» (GitLab)
    s = s.replace("Z", "+00:00")
    if re.match(r"\d{4}-\d{2}-\d{2} \d", s):
        s = s.replace(" ", "T", 1)
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)   # nanoseconds (Alertmanager)
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.year < 1971:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _h(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _lines(*pairs) -> str:
    return "\n".join(f"{k}: {v}" for k, v in pairs if v not in (None, "", [], {}))


# --- the emitters ----------------------------------------------------------------------------------

def alertmanager(body: dict, headers: dict, cfg: dict) -> list[Event]:
    """Prometheus Alertmanager (webhook_config, payload version 4): one event per alert in the group."""
    out = []
    for a in body.get("alerts") or []:
        labels, ann = a.get("labels") or {}, a.get("annotations") or {}
        name = labels.get("alertname") or "alert"
        target = labels.get("instance") or labels.get("host") or labels.get("job") or ""
        resolved = a.get("status") == "resolved"
        rest = ", ".join(f"{k}={v}" for k, v in sorted(labels.items()) if k not in ("alertname", "instance"))
        out.append(Event("resolved" if resolved else "firing", f"{name} · {target}" if target else name,
                         _lines(("summary", ann.get("summary")), ("description", ann.get("description")), ("severity", labels.get("severity")),
                                ("labels", rest)),
                         ts(a.get("endsAt")) if resolved else ts(a.get("startsAt")), a.get("fingerprint") or _h(sorted(labels.items()))))
    return out


def checkmk(body: dict, headers: dict, cfg: dict) -> list[Event]:
    """CheckMK, through the notification script in integrations/checkmk: the notification context (HOSTNAME, SERVICEDESC,
    NOTIFICATIONTYPE…). PROBLEM opens an alert and RECOVERY resolves it; acknowledgements, downtimes and flapping are left out."""
    b = {k.removeprefix("NOTIFY_").upper(): v for k, v in body.items()}
    kind = (b.get("NOTIFICATIONTYPE") or "").upper()
    if kind not in ("PROBLEM", "RECOVERY"):
        return []
    host, svc = b.get("HOSTNAME") or "?", b.get("SERVICEDESC") or ""
    service = (b.get("WHAT") or ("SERVICE" if svc else "HOST")).upper() == "SERVICE" and svc
    state = (b.get("SERVICESTATE") if service else b.get("HOSTSTATE")) or ""
    output = (b.get("SERVICEOUTPUT") if service else b.get("HOSTOUTPUT")) or ""
    return [Event("firing" if kind == "PROBLEM" else "resolved", f"{svc} · {host}" if service else host,
                  _lines(("state", state), ("output", output)), ts(b.get("MICROTIME")) or ts(b.get("LONGDATETIME")) or ts(b.get("SHORTDATETIME")),
                  _h("checkmk", host, svc if service else ""))]


def uptime_kuma(body: dict, headers: dict, cfg: dict) -> list[Event]:
    """Uptime Kuma (notification «Webhook», JSON body): DOWN opens an alert and UP resolves it; the test notification is an event."""
    hb, mon = body.get("heartbeat") or {}, body.get("monitor") or {}
    if not hb:
        return [Event("event", "Uptime Kuma", body.get("msg") or "")] if body.get("msg") else []
    status = hb.get("status")
    if status not in (0, 1):   # pending or maintenance: nothing final to remember
        return []
    name = mon.get("name") or f"monitor {hb.get('monitorID')}"
    return [Event("firing" if status == 0 else "resolved", name, _lines(("message", hb.get("msg")), ("url", mon.get("url") or mon.get("hostname"))),
                  ts(hb.get("time")), _h("kuma", mon.get("id") or hb.get("monitorID") or name))]


def proxmox(body: dict, headers: dict, cfg: dict) -> list[Event]:
    """Proxmox VE webhook target, with the JSON body documented in the wiki (title, message, severity, timestamp, fields): one event."""
    if not body.get("title") and not body.get("message"):
        return []
    f = body.get("fields") or {}
    return [Event("event", body.get("title") or (body.get("message") or "")[:120],
                  _lines(("severity", body.get("severity")), ("host", f.get("hostname")), ("type", f.get("type")), ("message", body.get("message"))),
                  ts(body.get("timestamp")))]


def github_actions(body: dict, headers: dict, cfg: dict) -> list[Event]:
    """GitHub (repository webhook): a finished workflow run (`workflow_run`, action completed) or a deployment status that is final
    (`deployment_status`). The kind comes in the X-GitHub-Event header."""
    kind = headers.get("x-github-event", "")
    repo = (body.get("repository") or {}).get("full_name") or "?"
    if kind == "workflow_run" and body.get("action") == "completed":
        r = body.get("workflow_run") or {}
        return [Event("event", f"{repo} · {r.get('name') or 'workflow'} · {r.get('conclusion') or '?'}",
                      _lines(("branch", r.get("head_branch")), ("commit", (r.get("head_sha") or "")[:12]), ("event", r.get("event")),
                             ("actor", (r.get("actor") or {}).get("login")), ("url", r.get("html_url"))),
                      ts(r.get("updated_at")) or ts(r.get("run_started_at")))]
    if kind == "deployment_status":
        s, d = body.get("deployment_status") or {}, body.get("deployment") or {}
        if s.get("state") not in ("success", "failure", "error", "inactive"):
            return []
        env = s.get("environment") or d.get("environment") or "?"
        return [Event("event", f"{repo} · deploy {env} · {s.get('state')}",
                      _lines(("ref", d.get("ref")), ("commit", (d.get("sha") or "")[:12]), ("description", s.get("description")),
                             ("by", (s.get("creator") or {}).get("login")), ("url", s.get("target_url") or s.get("log_url"))),
                      ts(s.get("updated_at")) or ts(s.get("created_at")))]
    return []


def gitlab_ci(body: dict, headers: dict, cfg: dict) -> list[Event]:
    """GitLab (project webhook): a pipeline or a deployment that has finished (success, failed or canceled)."""
    kind, proj = body.get("object_kind"), (body.get("project") or {}).get("path_with_namespace") or "?"
    final = ("success", "failed", "canceled")
    if kind == "pipeline":
        p = body.get("object_attributes") or {}
        if p.get("status") not in final:
            return []
        return [Event("event", f"{proj} · pipeline {p.get('ref') or ''} · {p.get('status')}".replace("  ", " "),
                      _lines(("commit", (p.get("sha") or "")[:12]), ("source", p.get("source")), ("duration", f"{p['duration']} s" if p.get("duration") else None),
                             ("by", (body.get("user") or {}).get("username")), ("url", p.get("url"))),
                      ts(p.get("finished_at")) or ts(p.get("created_at")))]
    if kind == "deployment":
        if body.get("status") not in final:
            return []
        return [Event("event", f"{proj} · deploy {body.get('environment') or '?'} · {body.get('status')}",
                      _lines(("ref", body.get("ref")), ("commit", body.get("short_sha")), ("by", (body.get("user") or {}).get("username")),
                             ("url", body.get("deployable_url"))),
                      ts(body.get("status_changed_at")))]
    return []


def _path(body, path: str):
    """A value by its dotted path (`alerts.0.labels.alertname`); None when it is not there."""
    cur = body
    for part in [p for p in (path or "").split(".") if p]:
        if isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def fill(template: str, body) -> str:
    """`{{a.b}}` placeholders replaced by the values of the body (lists and objects as JSON); missing values become empty."""
    def one(m):
        v = _path(body, m.group(1).strip())
        return "" if v is None else v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return re.sub(r"\{\{\s*([^{}]+?)\s*\}\}", one, template or "").strip()


def generic(body: dict, headers: dict, cfg: dict) -> list[Event]:
    """Any JSON: `title` and `text` with `{{path}}` placeholders, and optionally `at`, `fingerprint` and `state` as paths. With `state`,
    the values in `resolved` (default: resolved, ok, up, recovery) close the alert; without it, every request is one event."""
    title = fill(cfg.get("title") or "{{title}}", body) or "webhook"
    text = fill(cfg.get("text") or "", body)
    at = ts(_path(body, cfg["at"])) if cfg.get("at") else None
    if not cfg.get("state"):
        return [Event("event", title[:300], text, at)]
    value = str(_path(body, cfg["state"]) or "").strip().lower()
    resolved = [str(x).lower() for x in cfg.get("resolved") or ["resolved", "ok", "up", "recovery"]]
    fp = str(_path(body, cfg["fingerprint"]) or "") if cfg.get("fingerprint") else title
    return [Event("resolved" if value in resolved else "firing", title[:300], text, at, _h("generic", fp))]


TEMPLATES = {"alertmanager": alertmanager, "checkmk": checkmk, "uptime_kuma": uptime_kuma, "proxmox": proxmox,
             "github_actions": github_actions, "gitlab_ci": gitlab_ci, "generic": generic}
LABELS = {"alertmanager": "Alertmanager", "checkmk": "CheckMK", "uptime_kuma": "Uptime Kuma", "proxmox": "Proxmox VE",
          "github_actions": "GitHub Actions", "gitlab_ci": "GitLab CI", "generic": "Genérica"}


def parse(template: str, body, headers: dict | None = None, cfg: dict | None = None) -> list[Event]:
    if not isinstance(body, dict):
        return []
    return TEMPLATES[template](body, {k.lower(): v for k, v in (headers or {}).items()}, cfg or {})
