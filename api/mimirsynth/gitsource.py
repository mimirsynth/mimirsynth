"""Git repositories as a document source (#118): README, docs, ADRs and changelogs of a repository, synced by commit.

How a sync reads the repository without downloading it whole:
- **A shallow, blobless clone** (`--depth 1 --filter=blob:none --no-checkout`) in the document volume brings the last commit and its
  trees, not the contents. Later syncs `fetch --depth 1` the branch the same way.
- **The tree is listed without sizes** (`ls-tree -r` without `-l`: asking for a size would download the content to measure it), and the
  files are chosen by path: the include patterns, never the fixed exclusions, and only the document types the index reads.
- **Only the chosen files that are new or changed are downloaded**, with a sparse checkout of exactly those paths. A file above the
  maximum document size is left out once it is on disk.

Safety:
- Only the protocols in `PROTOCOLS` are allowed (`https`, `http`): no `ssh`, `file` or `ext::`. The address cannot carry a user or a
  password; a read-only token goes in an `Authorization` header scoped to that address, passed in the environment (never in the
  command line nor in `.git/config`), and only over https.
- Git runs without the system or user configuration (no credential helpers, no prompts), without hooks from the repository, without
  symbolic links and without Git LFS downloads.
- If anything fails, the caller deletes nothing: the documents already indexed stay.
"""
import base64
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

from . import docstore
from .i18n import SOURCE, tr  # tr(…, SOURCE): the Spanish text, marked so the API translates it when it answers with it

PROTOCOLS = ("https", "http")
DEFAULT_INCLUDE = ["README*", "docs/**", "**/adr/**", "CHANGELOG*"]
# file names that hold credentials by nature, at any depth; they are left out whatever the include patterns say
EXCLUDE = [".env*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.kdbx", "id_rsa*", "id_dsa*", "id_ecdsa*",
           "id_ed25519*", "credentials*", "*.tfstate*", ".netrc", ".npmrc", ".pypirc"]
MAX_FILES = 2000          # files the include patterns may select
MAX_TOTAL_MB = 200        # what one sync may download
MAX_PATTERNS = 50
TIMEOUT = 600             # seconds for one git command
_BRANCH = re.compile(r"^(?!-)(?!.*\.\.)(?!.*//)[A-Za-z0-9._/-]{1,200}(?<![/.])$")


class GitError(Exception):
    """Git could not do it; the message is shown to the administrator and never carries the token."""


@dataclass
class Synced:
    commit: str
    committed_at: datetime


# --- what the administrator gives -------------------------------------------------------------

def check_url(url: str) -> str:
    u = (url or "").strip()
    parts = urlsplit(u)
    if parts.scheme not in PROTOCOLS or u.startswith("-") or any(c.isspace() for c in u):
        raise ValueError(tr("la dirección del repositorio debe empezar por https:// o http://", SOURCE))
    if parts.scheme in ("http", "https") and (not parts.hostname or "@" in parts.netloc):
        raise ValueError(tr("la dirección del repositorio no puede llevar usuario ni contraseña: usa el campo del token", SOURCE))
    return u


def check_branch(branch: str) -> str:
    b = (branch or "").strip()
    if b and not _BRANCH.match(b):
        raise ValueError(tr("el nombre de la rama no es válido", SOURCE))
    return b


def check_include(patterns: list[str] | None) -> list[str]:
    out = []
    for p in patterns if patterns is not None else DEFAULT_INCLUDE:
        p = p.strip().removeprefix("./")
        if not p:
            continue
        if len(p) > 200 or p.startswith("/") or ".." in p.split("/") or any(ord(c) < 32 for c in p):
            raise ValueError(tr("la ruta «{{path}}» no es válida: relativa a la raíz del repositorio, sin «..»", SOURCE, path=p[:60]))
        out.append(p)
    if not out:
        raise ValueError(tr("indica al menos una ruta que incluir", SOURCE))
    if len(out) > MAX_PATTERNS:
        raise ValueError(tr("como mucho {{max}} rutas", SOURCE, max=MAX_PATTERNS))
    return list(dict.fromkeys(out))


# --- choosing the files -----------------------------------------------------------------------

def _rx(pattern: str) -> re.Pattern:
    """A path pattern: `*` and `?` stay inside one folder, `**` crosses folders. Matched against the whole path from the root."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        else:
            c = pattern[i]
            out += "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c)
            i += 1
    return re.compile(out + r"\Z", re.IGNORECASE)


def included(path: str, patterns: list[str]) -> bool:
    return any(_rx(p).match(path) for p in patterns)


def excluded(path: str) -> bool:
    """Hidden files and folders, and the names in EXCLUDE at any depth."""
    parts = path.split("/")
    return any(x.startswith(".") for x in parts[:-1]) or any(_rx(p).match(parts[-1]) for p in EXCLUDE) or parts[-1].startswith(".")


def select(entries: list[tuple[str, str, str]], include: list[str]) -> dict[str, str]:
    """{path: blob} of the files to index, from `(mode, blob, path)` entries: regular files only (no links, no submodules)."""
    out = {}
    for mode, blob, path in entries:
        if mode not in ("100644", "100755") or len(path) > 480:
            continue
        if docstore.ext_of(path) in docstore.ALLOWED_EXT and included(path, include) and not excluded(path):
            out[path] = blob
    return out


# --- links to the forge -----------------------------------------------------------------------

def web_base(url: str) -> str | None:
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    return f"{p.scheme}://{p.netloc}{p.path.rstrip('/').removesuffix('.git')}"


def web_link(url: str, commit: str, path: str) -> str | None:
    """The file at that commit in the forge's web view, when the address tells which forge it is (GitHub-style otherwise)."""
    base = web_base(url)
    if not base:
        return None
    host = (urlsplit(url).hostname or "").lower()
    if "dev.azure.com" in host or host.endswith("visualstudio.com"):
        return None
    q = quote(path)
    if "gitlab" in host:
        return f"{base}/-/blob/{commit}/{q}"
    if host == "bitbucket.org":
        return f"{base}/src/{commit}/{q}"
    if host == "codeberg.org" or "gitea" in host or "forgejo" in host:
        return f"{base}/src/commit/{commit}/{q}"
    return f"{base}/blob/{commit}/{q}"


# --- running git ------------------------------------------------------------------------------

def _env(url: str, token: str = "", username: str = "") -> dict[str, str]:
    conf = [("protocol.allow", "never"), *((f"protocol.{p}.allow", "always") for p in PROTOCOLS), ("credential.helper", ""),
            ("core.symlinks", "false"), ("core.autocrlf", "false"), ("core.hooksPath", os.devnull), ("advice.detachedHead", "false"),
            ("submodule.recurse", "false"), ("fetch.recurseSubmodules", "false")]
    if token:
        if urlsplit(url).scheme != "https":
            raise ValueError(tr("el token solo se envía por https", SOURCE))
        basic = base64.b64encode(f"{username.strip() or 'x-access-token'}:{token}".encode()).decode()
        conf.append((f"http.{url}.extraHeader", f"Authorization: Basic {basic}"))
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_LFS_SKIP_SMUDGE="1", GIT_ASKPASS="",
               GIT_CONFIG_COUNT=str(len(conf)))
    for i, (k, v) in enumerate(conf):
        env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"] = k, v
    return env


def _git(args: list[str], env: dict, cwd: Path | None = None, stdin: str | None = None) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, env=env, input=stdin, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TIMEOUT)
    except FileNotFoundError:
        raise GitError("git no está instalado en el servidor") from None
    except subprocess.TimeoutExpired:
        raise GitError(f"git tardó más de {TIMEOUT // 60} minutos") from None
    if r.returncode != 0:
        lines = [x.strip() for x in (r.stderr or "").splitlines() if x.strip() and not x.lower().startswith(("hint:", "warning:"))]
        raise GitError(" ".join(lines)[-300:] or f"git terminó con el código {r.returncode}")
    return r.stdout


def probe(url: str, branch: str, token: str = "", username: str = "") -> None:
    """Checks the address, the token and the branch before saving anything (`ls-remote`, nothing is downloaded)."""
    out = _git(["ls-remote", "--", url, f"refs/heads/{branch}" if branch else "HEAD"], _env(url, token, username))
    if not out.strip():
        raise GitError(f"la rama «{branch}» no existe en el repositorio" if branch else "el repositorio está vacío")


def repo_dir(brain_id: int, source_id: int) -> Path:
    return docstore.root() / str(int(brain_id)) / str(int(source_id)) / "_git"


def fetch(brain_id: int, source_id: int, url: str, branch: str, token: str = "", username: str = "") -> tuple[Path, Synced]:
    """Brings the last commit of the branch (or of the default branch) into the source's clone, making it the first time."""
    d, env = repo_dir(brain_id, source_id), _env(url, token, username)
    if (d / ".git").is_dir() and _origin(d, env) == url:
        _git(["fetch", "-q", "--depth", "1", "--no-tags", "origin", branch or "HEAD"], env, d)
        ref = "FETCH_HEAD"
    else:
        _rmtree(d)
        d.parent.mkdir(parents=True, exist_ok=True)
        try:
            _git(["clone", "-q", "--depth", "1", "--filter=blob:none", "--no-checkout", "--no-tags", "--single-branch",
                  *(["--branch", branch] if branch else []), "--", url, str(d)], env)
        except GitError:
            _rmtree(d)
            raise
        ref = "HEAD"
    commit = _git(["rev-parse", ref], env, d).strip()
    when = datetime.fromisoformat(_git(["log", "-1", "--format=%cI", commit], env, d).strip())
    return d, Synced(commit, when.astimezone(timezone.utc))


def tree(d: Path, commit: str, url: str) -> list[tuple[str, str, str]]:
    """(mode, blob, path) of every file at that commit, from the trees alone: no content is downloaded."""
    out = []
    for item in _git(["ls-tree", "-r", "-z", "--full-tree", commit], _env(url), d).split("\0"):
        if "\t" in item:
            head, path = item.split("\t", 1)
            mode, kind, blob = head.split(" ")
            if kind == "blob":
                out.append((mode, blob, path))
    return out


def _literal(path: str) -> str:
    """A path as a sparse-checkout pattern that matches only itself."""
    return "/" + "".join("\\" + c if c.isascii() and not (c.isalnum() or c in "/._-") else c for c in path)


def checkout(d: Path, commit: str, paths: list[str], url: str, token: str = "", username: str = "") -> None:
    """Puts exactly those files of that commit on disk, downloading only their contents (one request for all)."""
    if not paths:
        return
    env = _env(url, token, username)
    _git(["sparse-checkout", "set", "--no-cone", "--stdin"], env, d, stdin="\n".join(_literal(p) for p in paths) + "\n")
    _git(["checkout", "-q", "-f", "--detach", commit], env, d)


def read(d: Path, path: str) -> bytes:
    p = (d / path)
    real = p.resolve()
    if d.resolve() not in real.parents or p.is_symlink() or not real.is_file():
        raise ValueError(f"{path}: no es un fichero del repositorio")
    return real.read_bytes()


def _origin(d: Path, env: dict) -> str:
    try:
        return _git(["config", "--get", "remote.origin.url"], env, d).strip()
    except GitError:  # a clone cut halfway: it is made again
        return ""


def _rmtree(d: Path) -> None:
    """Git keeps its packs read-only; on Windows that stops a plain rmtree."""
    def force(func, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    if d.exists():
        shutil.rmtree(d, **({"onexc": force} if sys.version_info >= (3, 12) else {"onerror": force}))


def remove(brain_id: int, source_id: int) -> None:
    _rmtree(repo_dir(brain_id, source_id))
