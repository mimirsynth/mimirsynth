"""Extrae los textos en español que el servidor muestra a las personas (errores de la API, ajustes, etiquetas de trabajos, política de
contraseñas) y a los agentes (herramientas del MCP y encabezados del recall, marcados con `i18n.tr`) para traducirlos en
`web/src/i18n/en.server.json`. Las claves con `{{nombre}}` son plantillas: la interfaz las reconoce
aunque el texto venga ya con los valores sustituidos.
Uso: `python -m mimirsynth.i18n_extract` (lista las claves) o `python -m mimirsynth.i18n_extract --missing` (las que faltan en el catálogo)."""
import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
CATALOG = HERE.parent.parent / "web" / "src" / "i18n" / "en.server.json"


def _base(expr: ast.AST) -> str:
    """Nombre legible del valor interpolado: la clave de un diccionario o de `get('x')`, o el último nombre de la expresión."""
    if isinstance(expr, ast.Subscript) and isinstance(expr.slice, ast.Constant) and isinstance(expr.slice.value, str):
        return expr.slice.value
    if isinstance(expr, ast.Call):
        for a in expr.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.isidentifier():
                return a.value
        return _base(expr.func.value) if isinstance(expr.func, ast.Attribute) and not isinstance(expr.func.value, ast.Constant) else "v"
    if isinstance(expr, ast.BoolOp):
        return _base(expr.values[0])
    if isinstance(expr, ast.Attribute):
        return expr.attr
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, (ast.Subscript, ast.Slice)):
        return _base(expr.value)
    return "v"


def _name(expr: ast.AST, used: set[str]) -> str:
    base = re.sub(r"\W", "", _base(expr)) or "v"
    n, i = base, 1
    while n in used:
        i += 1
        n = f"{base}{i}"
    used.add(n)
    return n


def _template(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        used: set[str] = set()
        out = ""
        for p in node.values:
            out += p.value if isinstance(p, ast.Constant) else "{{" + _name(p.value, used) + "}}"
        return out
    return None


def _has_text(s: str) -> bool:
    return bool(re.search(r"[A-Za-zÁÉÍÓÚáéíóúñ]{3,}", s.replace("{{", "").replace("}}", "")))


def collect() -> set[str]:
    keys: set[str] = set()
    for f in sorted(HERE.glob("*.py")):
        if f.name == Path(__file__).name:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                fn = getattr(n.func, "id", getattr(n.func, "attr", ""))
                if fn == "HTTPException" and len(n.args) >= 2:
                    t = _template(n.args[1])
                    if t and _has_text(t):
                        keys.add(t)
                elif fn == "tr" and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                    keys.add(n.args[0].value)  # i18n.tr("texto con {{valores}}", lang, …)
                elif fn == "Rule" and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant):
                    keys.add(n.args[1].value)  # secretscan.Rule("id", "etiqueta", …): tipo de secreto que ven personas y agentes
                elif fn == "register" and len(n.args) >= 2 and getattr(n.func, "attr", "") == "register":
                    t = _template(n.args[1])  # jobs.register("kind", "Etiqueta")
                    if t:
                        keys.add(t)
                elif fn == "Def" and f.name == "appsettings.py":
                    for a in (n.args[2:4] + n.args[5:6]):  # etiqueta, ayuda y unidad
                        t = _template(a)
                        if t:
                            keys.add(t)
                    for kw in n.keywords:
                        if kw.arg == "choices" and isinstance(kw.value, (ast.Tuple, ast.List)):
                            for c in kw.value.elts:
                                if isinstance(c, (ast.Tuple, ast.List)) and len(c.elts) == 2:
                                    t = _template(c.elts[1])
                                    if t:
                                        keys.add(t)
        if f.name == "appsettings.py":
            for n in ast.walk(tree):
                if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "GROUPS" for t in n.targets) and isinstance(n.value, ast.Dict):
                    keys.update(v.value for v in n.value.values if isinstance(v, ast.Constant))
        if f.name == "mcp_server.py":  # títulos y descripciones de las herramientas (y de sus parámetros)
            tools = [n.value for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "TOOLS" for t in n.targets)]
            for n in (d for t in tools for d in ast.walk(t)):
                if isinstance(n, ast.Dict):
                    for k, v in zip(n.keys, n.values):
                        if isinstance(k, ast.Constant) and k.value in ("title", "description") and isinstance(v, ast.Constant) and isinstance(v.value, str):
                            keys.add(v.value)
        if f.name == "passwords.py":
            for n in ast.walk(tree):
                if isinstance(n, ast.Return) and n.value is not None:
                    t = _template(n.value)
                    if t and _has_text(t):
                        keys.add(t)
    return keys


if __name__ == "__main__":
    keys = collect()
    if "--missing" in sys.argv:
        have = set(json.loads(CATALOG.read_text(encoding="utf-8"))) if CATALOG.exists() else set()
        keys = {k for k in keys if k not in have}
        print(json.dumps({k: "" for k in sorted(keys)}, ensure_ascii=False, indent=1))
    else:
        print("\n".join(sorted(keys)))
