"""Entity hygiene at extraction (#467): names the LLM extracts that are a detail of a fact, never an entity of their own, are dropped
before graphiti-core resolves and writes them. The edges are then extracted among the entities that remain, so the detail stays in
the text of their facts («run the vault tool with --help on the Ops host» is a fact about the tool and the host, not about an entity
«--help flag»). When the dropped name was the only other end of a fact, that fact is not created: the episode keeps the sentence,
and recall still finds it among the episode's fragments.

What is dropped, by kind: a command-line flag, a field path in code, a file path or source file, a URL, a date alone, and a clause
(five or more words starting with a lower-case word, most of them not capitalised). Kept on purpose: host names (`api.example.com`),
products written like files (`Node.js`, `three.js`, `Newtonsoft.Json`, `docs.rs`), systemd units (`nginx.service`), dotted .NET
namespaces (`Microsoft.AspNetCore`), `TCP/IP`, proper names that start with a particle («el Ministerio de Sanidad y Consumo»),
versioned products («Debian 13»), bare versions («3.12.10») and `key=value` names, which the type corrector reviews instead. The
rules err on the side of keeping: a missed detail is still caught later by the corrector, a dropped entity is not."""
from __future__ import annotations

import contextvars
import logging
import re

log = logging.getLogger("mimirsynth.hygiene")

KINDS = ("flag", "field", "path", "url", "date", "clause")
_MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|"
           "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre")
_DAY = r"\d{1,2}(st|nd|rd|th)?"
_DATE = re.compile(
    r"^(\d{4}[-/]\d{1,2}([-/]\d{1,2})?([T ]\d{1,2}:\d{2}(:\d{2})?)?"          # 2026-10-01, 2026/10/01, 2026-10, with a time
    r"|\d{1,2}([/-])\d{1,2}\5(\d{2}|\d{4})"                                     # 01/10/2026, 1-10-26
    r"|\d{1,2}\.\d{1,2}\.\d{4}"                                                 # 01.10.2026 (a bare «3.12.10» is a version)
    rf"|((el|the)\s+)?({_DAY}\s+((of|de)\s+)?)?({_MONTHS})\.?,?(\s+{_DAY},?)?(\s+((de|del|of)\s+)?\d{{4}})?"   # 1st of October 2026, el 1 de octubre
    r")$", re.I)
_FLAG_WORD = r"(\s+(flag|option|opción|parameter|parámetro|switch))"
_FLAG = re.compile(rf"^--?[A-Za-z][\w-]*{_FLAG_WORD}?$"                          # --help, -config-file flag
                   rf"|^\S+(\s+\S+)?\s+--[A-Za-z][\w-]*{_FLAG_WORD}?$"           # tool --help, tool --help flag
                   rf"|^\S+(\s+\S+)?\s+-[a-z][\w-]*{_FLAG_WORD}$", re.I)         # tool -v flag (not «AC -DC», «Plan -B»)
_URL = re.compile(r"^(https?|ftp|ssh|git)://\S+$|^www\.\S+$", re.I)
# a host and a path with no scheme («github.com/org/repo»): written in lower case, as hosts are; «Node.js/Express» is two products
_HOST_PATH = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}/\S*$")
# with a directory, any of these; a bare name only with an extension that is not also how products are named (.js, .rs, .sh, .io…)
_EXT = re.compile(r"\.(py|js|mjs|cjs|ts|tsx|jsx|go|rs|java|kt|rb|php|c|h|cpp|hpp|cs|json|ya?ml|toml|ini|cfg|conf|env|sh|bash|ps1|md|txt|log|"
                  r"html|css|scss|sql|service|socket|timer|lock|xml|csv)$")
_BARE_EXT = re.compile(r"\.(py|ya?ml|toml|ini|cfg|conf|env|ps1|txt|log|sql|lock|csv|md)$")
_FIELD = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+(\(\))?$")
_RECEIVERS = {"self", "this", "cls"}
_PARTICLES = {"a", "an", "the", "of", "to", "from", "in", "on", "at", "for", "with", "by", "and", "or", "per", "into", "over",
              "de", "del", "la", "el", "los", "las", "en", "con", "por", "para", "y", "o", "al", "un", "una", "van", "der", "den", "von",
              "da", "di", "le", "du", "des"}


def _path(n: str) -> bool:
    if " " in n:
        return False
    if n.startswith(("/", "./", "../", "~/")) or re.match(r"^[A-Za-z]:\\", n) or (n.endswith("/") and len(n) > 1):
        return True
    if "/" in n or "\\" in n:
        return bool(_EXT.search(n))
    return bool(_BARE_EXT.search(n))     # «README.md», «docker-compose.yml»; not «three.js», «Newtonsoft.Json», «docs.rs»


def _field(n: str) -> bool:
    """A field or call in code: `SectionVMInfo.uptime`, `config.max_retries`, `self.db`, `os.path.join()`, `obj.maxRetries`. A host
    name, a product or a namespace (`api.example.com`, `Node.js`, `Microsoft.AspNetCore`, `pandas.DataFrame`) is none of those."""
    if not _FIELD.match(n):
        return False
    parts = n.rstrip("()").split(".")
    last = parts[-1]
    return (n.endswith("()") or parts[0] in _RECEIVERS or any("_" in p for p in parts)
            or any(p[:1].islower() and re.search(r"[a-z][A-Z]", p) for p in parts[1:])        # obj.maxRetries
            # SectionVMInfo.uptime: a type with capitals inside and a member; not «Proxmox.local», «Django.contrib»
            or (bool(re.search(r"[a-z][A-Z]|[A-Z]{2}[a-z]", parts[0])) and last[:1].islower() and len(last) > 3))


def _clause(n: str) -> bool:
    """Five or more words, the first a lower-case word, and most of the rest not capitalised: a phrase («sync push from A to B»,
    «budget limit of 5 dollars a month»). A proper name that starts with a particle («el Ministerio de Sanidad y Consumo», «de
    Havilland Aircraft Company») has most of its words capitalised."""
    words = n.split()
    if len(words) < 5 or not re.fullmatch(r"[a-zß-öø-ÿ]+", words[0]):
        return False
    content = [w for w in words if w.lower() not in _PARTICLES]
    caps = sum(1 for w in content if w[:1].isupper())
    return caps * 2 <= len(content)


def kind(name: str | None) -> str | None:
    """Why this extracted name is not an entity, or None when it may be one."""
    n = " ".join(str(name or "").split())
    if not n:
        return None
    if _URL.match(n) or _HOST_PATH.match(n):
        return "url"
    if _FLAG.match(n):
        return "flag"
    if _path(n):
        return "path"
    if _field(n):
        return "field"
    if _DATE.match(n) and re.search(r"\d", n):   # a month alone («May», «March») may be a name
        return "date"
    if _clause(n):
        return "clause"
    return None


# The counts of the ingestion in progress: set by ingest around `add_episode`, read back into its report.
dropped: contextvars.ContextVar[dict | None] = contextvars.ContextVar("mimirsynth_not_entities", default=None)


def install() -> bool:
    """Wraps the `extract_nodes` that graphiti-core's `add_episode` calls, once per process. Returns False (and logs) if a
    graphiti-core upgrade moved it, so extraction goes on unfiltered instead of failing."""
    import inspect
    import graphiti_core.graphiti as gg
    orig = getattr(gg, "extract_nodes", None)
    if getattr(orig, "_mimirsynth_hygiene", False):
        return True
    if orig is None or not inspect.iscoroutinefunction(orig):
        log.warning("graphiti-core no longer has extract_nodes: names that are not entities are written again")
        return False

    async def wrapped(*args, **kwargs):
        nodes, index = await orig(*args, **kwargs)
        return filter_nodes(nodes, index)
    wrapped._mimirsynth_hygiene = True
    gg.extract_nodes = wrapped
    return True


def filter_nodes(nodes: list, index: dict) -> tuple[list, dict]:
    """The extracted nodes without those that are not entities, counted by kind in the ingestion's report."""
    keep, counts = [], dropped.get()
    for n in nodes:
        k = kind(getattr(n, "name", ""))
        if k is None:
            keep.append(n)
            continue
        if counts is not None:
            counts[k] = counts.get(k, 0) + 1
        if isinstance(index, dict):
            index.pop(str(getattr(n, "uuid", "")), None)
    return keep, index
