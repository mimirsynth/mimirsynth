"""Git repositories as a document source (#118): README, docs, ADRs and changelogs of a repository, synced by commit.

How a sync reads the repository without downloading it whole:
- **A shallow, blobless clone** (`--depth 1 --filter=blob:none --no-checkout`) in the document volume brings the last commit and its
  trees, not the contents. Later syncs `fetch --depth 1` the branch the same way.
- **The tree is listed without sizes** (`ls-tree -r` without `-l`: asking for a size would download the content to measure it), and the
  files are chosen by path: the include patterns, never the fixed exclusions, and only the document types the index reads. A pattern
  that names a folder (no `*` or `?` in its last part) takes everything inside it, as in `.gitignore`.
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
import tempfile
import unicodedata
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
PREVIEW_TIMEOUT = 60      # the check made when saving waits less: if it does not finish, saving goes on and the sync reports
MAX_TOP = 30              # top-level folders named when the paths select nothing
_BRANCH = re.compile(r"^(?!-)(?!.*\.\.)(?!.*//)[A-Za-z0-9._/-]{1,200}(?<![/.])$")


class GitError(Exception):
    """Git could not do it; the message is shown to the administrator and never carries the token."""


@dataclass
class Synced:
    commit: str
    committed_at: datetime


@dataclass
class Matched:
    """What the include paths select in a tree: the files, how many each path takes, and the top-level folders (to help when it
    is none)."""
    picked: dict[str, str]
    counts: dict[str, int]
    top: list[str]

    def empty_message(self) -> str:
        return tr("Ningún fichero coincide con las rutas elegidas. Carpetas de primer nivel del repositorio: {{folders}}.", SOURCE,
                  folders=folders(self.top))


def folders(top: list[str]) -> str:
    return ", ".join(top) + (" …" if len(top) >= MAX_TOP else "") if top else "—"


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
        out.append(_tidy(p))
    if not out:
        raise ValueError(tr("indica al menos una ruta que incluir", SOURCE))
    if len(out) > MAX_PATTERNS:
        raise ValueError(tr("como mucho {{max}} rutas", SOURCE, max=MAX_PATTERNS))
    return list(dict.fromkeys(out))


# --- choosing the files -----------------------------------------------------------------------
# Patterns are matched folder by folder, without regular expressions: a regex built from `**` nests `.*` and can backtrack for a very
# long time on a long path, holding the only process (as the secret detector once did, #138). Both steps below are polynomial.

def _tidy(pattern: str) -> str:
    """Empty folders and repeated `**` folders say nothing more: `docs//**/**/x` is `docs/**/x`."""
    out: list[str] = []
    for seg in pattern.split("/"):
        if seg and not (seg == "**" and out and out[-1] == "**"):
            out.append(seg)
    return "/".join(out)


def _name(pattern: str, name: str) -> bool:
    """One folder or file name against one segment of a pattern: `*` any run of characters, `?` one. Linear in practice, never
    worse than len(pattern) × len(name): on a mismatch it only goes back to the last `*`."""
    p, n = pattern.lower(), name.lower()
    i = j = 0
    star, mark = -1, 0
    while j < len(n):
        if i < len(p) and (p[i] == "?" or p[i] == n[j]):
            i, j = i + 1, j + 1
        elif i < len(p) and p[i] == "*":
            star, mark, i = i, j, i + 1
        elif star >= 0:
            mark += 1
            i, j = star + 1, mark
        else:
            return False
    return all(c == "*" for c in p[i:])


def _match(pattern: str, path: str) -> bool:
    """The whole path against a pattern from the root: a `**` folder is zero or more folders (one or more at the end, as in
    gitignore); `*` and `?` stay inside one name, and a `**` inside a name is just `*`."""
    ps, ns = pattern.split("/"), path.split("/")
    seen: dict[tuple[int, int], bool] = {}

    def at(i: int, j: int) -> bool:
        if (i, j) not in seen:
            if i == len(ps):
                ok = j == len(ns)
            elif ps[i] == "**" and i == len(ps) - 1:  # a final `**` is whatever is inside, not the folder itself
                ok = j < len(ns)
            elif ps[i] == "**":
                ok = at(i + 1, j) or (j < len(ns) and at(i, j + 1))
            else:
                ok = j < len(ns) and _name(ps[i], ns[j]) and at(i + 1, j + 1)
            seen[(i, j)] = ok
        return seen[(i, j)]
    return at(0, 0)


def _nfc(s: str) -> str:
    """A name typed on one system and committed from another can come composed or decomposed («í» or «i» + accent): both are the same."""
    return unicodedata.normalize("NFC", s)


def _hit(pattern: str, path: str) -> bool:
    """One include path against one file. A path whose last part has no `*` or `?` also takes everything inside it as a folder:
    `Fullstack` and `Fullstack/` are `Fullstack/**`, as in `.gitignore` or a sparse checkout; a file named that way still matches."""
    p, f = _tidy(_nfc(pattern)), _nfc(path)
    if not p:
        return False
    if _match(p, f):
        return True
    last = p.rsplit("/", 1)[-1]
    return last != "**" and not any(c in last for c in "*?") and _match(p + "/**", f)


def included(path: str, patterns: list[str]) -> bool:
    return any(_hit(p, path) for p in patterns)


def excluded(path: str) -> bool:
    """Hidden files and folders, and the names in EXCLUDE at any depth."""
    parts = path.split("/")
    return any(x.startswith(".") for x in parts) or any(_name(p, parts[-1]) for p in EXCLUDE)


def select(entries: list[tuple[str, str, str]], include: list[str]) -> dict[str, str]:
    """{path: blob} of the files to index, from `(mode, blob, path)` entries: regular files only (no links, no submodules)."""
    return match(entries, include).picked


def match(entries: list[tuple[str, str, str]], include: list[str]) -> Matched:
    """The files to index and, for each include path, how many of the files that could come in it takes (one file can count
    under several paths)."""
    picked: dict[str, str] = {}
    counts = dict.fromkeys(include, 0)
    for mode, blob, path in entries:
        if mode not in ("100644", "100755") or len(path) > 480 or not docstore.scannable(path) or excluded(path):
            continue
        hits = [p for p in include if _hit(p, path)]
        for p in hits:
            counts[p] += 1
        if hits:
            picked[path] = blob
    top = sorted({path.split("/", 1)[0] for _, _, path in entries if "/" in path and not path.startswith(".")}, key=str.lower)
    return Matched(picked, counts, top[:MAX_TOP])


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


def _git(args: list[str], env: dict, cwd: Path | None = None, stdin: str | None = None, timeout: int = TIMEOUT) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, env=env, input=stdin, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except FileNotFoundError:
        raise GitError("git no está instalado en el servidor") from None
    except subprocess.TimeoutExpired:
        raise GitError(f"git tardó más de {timeout} segundos") from None
    if r.returncode != 0:
        lines = [x.strip() for x in (r.stderr or "").splitlines() if x.strip() and not x.lower().startswith(("hint:", "warning:"))]
        raise GitError(" ".join(lines)[-300:] or f"git terminó con el código {r.returncode}")
    return r.stdout


def probe(url: str, branch: str, token: str = "", username: str = "") -> None:
    """Checks the address, the token and the branch before saving anything (`ls-remote`, nothing is downloaded)."""
    out = _git(["ls-remote", "--", url, f"refs/heads/{branch}" if branch else "HEAD"], _env(url, token, username))
    if not out.strip():
        raise GitError(f"la rama «{branch}» no existe en el repositorio" if branch else "el repositorio está vacío")


def preview(url: str, branch: str, include: list[str], token: str = "", username: str = "") -> Matched | None:
    """What the paths would select, checked when saving: the trees of the last commit in a throwaway clone (no contents). None if
    it could not be checked in time: saving goes on and the sync reports it."""
    d = Path(tempfile.mkdtemp(prefix="mimirsynth-git-"))
    env = _env(url, token, username)
    try:
        _git(["clone", "-q", "--depth", "1", "--filter=blob:none", "--no-checkout", "--no-tags", "--single-branch",
              *(["--branch", branch] if branch else []), "--", url, str(d / "r")], env, timeout=PREVIEW_TIMEOUT)
        return match(tree(d / "r", "HEAD", url), include)
    except GitError:
        return None
    finally:
        _rmtree(d)


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
