"""Entity hygiene at extraction (#467): names the LLM extracts that are a detail of a fact, never an entity of their own, are dropped
before graphiti-core resolves and writes them. The edges are then extracted among the entities that remain, so the detail stays in
the fact's text («run the tool with --help» is a fact about the tool, not an entity «--help flag»).

What is dropped, by kind: a command-line flag, a dotted field path, a file path or source file, a URL, a date alone, and a clause
(five or more words starting in lower case). Kept on purpose: host names (`api.example.com`), `Node.js`, `TCP/IP`, proper names of
five or more words («Ministry of Health and Social Services»), versioned products («Debian 13») and `key=value` names, which the type
corrector reviews instead."""
from __future__ import annotations

import contextvars
import logging
import re

log = logging.getLogger("mimirsynth.hygiene")

KINDS = ("flag", "field", "path", "url", "date", "clause")
_MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|"
           "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre")
_DATE = re.compile(
    r"^(\d{4}-\d{1,2}(-\d{1,2})?([T ]\d{1,2}:\d{2}(:\d{2})?)?"             # 2026-10-01, 2026-10, with a time
    r"|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"                                       # 01/10/2026
    rf"|(\d{{1,2}}(st|nd|rd|th)?\s+(de\s+)?)?({_MONTHS})\.?,?(\s+(de\s+)?\d{{1,2}}(st|nd|rd|th)?,?)?(\s+(de\s+|del\s+)?\d{{4}})?"   # 1 October 2026, octubre de 2026
    r")$", re.I)
_FLAG = re.compile(r"^--?[A-Za-z][\w-]*(\s+(flag|option|opción|parameter|parámetro|switch))?$"
                   r"|^\S+(\s+\S+)?\s+--?[A-Za-z][\w-]*(\s+(flag|option|opción|parameter|parámetro|switch))?$", re.I)
_URL = re.compile(r"^(https?|ftp|ssh|git)://\S+$|^www\.\S+$", re.I)
_EXT = re.compile(r"\.(py|js|mjs|cjs|ts|tsx|jsx|go|rs|java|kt|rb|php|c|h|cpp|hpp|cs|json|ya?ml|toml|ini|cfg|conf|env|sh|bash|ps1|md|txt|log|"
                  r"html|css|scss|sql|service|socket|timer|lock|xml|csv)$", re.I)
_FIELD = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+(\(\))?$")


def _path(n: str) -> bool:
    if " " in n:
        return False
    if n.startswith(("/", "./", "../", "~/")) or re.match(r"^[A-Za-z]:\\", n):
        return True
    m = _EXT.search(n)
    if not m:
        return False
    if "/" in n or "\\" in n:
        return True
    # a bare file name («README.md», «docker-compose.yml»), but not a product named like one («Node.js», «Vue.js»)
    return not (m.group(1).lower() == "js" and n[:1].isupper())


def _field(n: str) -> bool:
    """`SectionVMInfo.uptime`, `config.max_retries`: a code identifier with a dot. A host name or a product (`api.example.com`,
    `Node.js`, `ASP.NET`) has no underscore and no camel case inside a part."""
    if not _FIELD.match(n) or _EXT.search(n):
        return False
    parts = n.rstrip("()").split(".")
    return any("_" in p or re.search(r"[a-z][A-Z]|[A-Z]{2}[a-z]", p) for p in parts)


def _clause(n: str) -> bool:
    """Five or more words whose first is a lower-case word: a phrase («sync push from A to B», «budget limit of 5 dollars a month»).
    A proper name starts in upper case («Ministry of Health and Social Services»), and so does a brand like «iPhone 15 Pro Max case»."""
    words = n.split()
    return len(words) >= 5 and bool(re.fullmatch(r"[a-zß-öø-ÿ]+", words[0]))


def kind(name: str | None) -> str | None:
    """Why this extracted name is not an entity, or None when it may be one."""
    n = " ".join(str(name or "").split())
    if not n:
        return None
    if _URL.match(n):
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
