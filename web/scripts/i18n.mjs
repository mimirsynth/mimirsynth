// Extrae las claves traducibles (t("…"), tr("…"), T("…")) y comprueba que el catálogo en.json las cubre todas y no tiene sobrantes.
// Un catálogo es su fichero más los fragmentos de su carpeta (en.json + en/*.json, en.server.json + en.server/*.json; ver catalogs.mjs):
// una PR añade sus textos en un fragmento nuevo y no toca el catálogo, así dos PR no chocan en las mismas líneas.
//   node scripts/i18n.mjs               comprueba (falla si faltan o sobran claves, si una clave está en dos ficheros o si uno no está en orden)
//   node scripts/i18n.mjs --list        lista las claves que faltan por traducir
//   node scripts/i18n.mjs --sort        ordena alfabéticamente cada fichero de los dos catálogos
//   node scripts/i18n.mjs --consolidate pasa los fragmentos a en.json y en.server.json, ordenados, y los borra (en la PR de una versión)
// Además prohíbe texto sin traducir en la interfaz: todo texto visible pasa por t()/tr()/T(). Excepción justificada: `// i18n-ok: motivo` en la línea.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseSync } from "oxc-parser";
import { consolidate, readCatalog, sortCatalog } from "./catalogs.mjs";

const ROOT = fileURLToPath(new URL("../src", import.meta.url));  // pathname daría «/C:/…» en Windows
const files = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => e.isDirectory() ? files(path.join(d, e.name)) : /\.tsx?$/.test(e.name) ? [path.join(d, e.name)] : []);
const keys = new Set();
const literal = [];
const TEXT_ATTRS = new Set(["label", "title", "description", "placeholder", "warning", "hint", "aria-label", "alt", "action"]);
for (const f of files(ROOT)) {
  if (f.includes(`${path.sep}i18n${path.sep}`)) continue;
  const text = fs.readFileSync(f, "utf8");
  const { program, errors } = parseSync(f, text, { lang: f.endsWith("x") ? "tsx" : "ts" });
  if (errors.length) { literal.push(`${path.relative(ROOT, f)}  no se pudo analizar: ${errors[0].message}`); continue; }
  const lines = text.split("\n");
  const lineOf = (pos) => text.slice(0, pos).split("\n").length - 1;
  const flag = (node, what) => { const ln = lineOf(node.start); if (!/i18n-ok/.test(lines[ln])) literal.push(`${path.relative(ROOT, f)}:${ln + 1}  ${what}`); };
  const isStr = (a) => a && ((a.type === "Literal" && typeof a.value === "string") || (a.type === "TemplateLiteral" && a.expressions.length === 0));
  const strOf = (a) => (a.type === "Literal" ? a.value : a.quasis[0].value.cooked);
  const visit = (n) => {
    if (!n || typeof n.type !== "string") return;
    if (n.type === "JSXText" && /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}/.test(text.slice(n.start, n.end).replace(/&[a-z]+;/g, ""))) flag(n, `texto sin traducir en JSX: ${JSON.stringify(text.slice(n.start, n.end).trim().slice(0, 50))}`);
    if (n.type === "JSXAttribute" && n.value && n.value.type === "Literal" && typeof n.value.value === "string" && n.name.type === "JSXIdentifier" && TEXT_ATTRS.has(n.name.name) && /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}/.test(n.value.value)) flag(n, `${n.name.name}="${n.value.value.slice(0, 40)}" sin traducir`);
    if (n.type === "CallExpression" && n.callee.type === "Identifier" && ["t", "tr", "T"].includes(n.callee.name) && isStr(n.arguments[0])) keys.add(strOf(n.arguments[0]));
    for (const k in n) {
      if (k === "parent") continue;
      const v = n[k];
      if (Array.isArray(v)) v.forEach(visit); else if (v && typeof v === "object") visit(v);
    }
  };
  visit(program);
}
const CATALOG = path.join(ROOT, "i18n", "en.json");
const SERVER = path.join(ROOT, "i18n", "en.server.json");  // its keys are checked against the API code by api/tests/test_i18n.py
if (process.argv.includes("--sort")) {
  for (const f of [CATALOG, SERVER]) sortCatalog(f);
  console.log("en.json y en.server.json, con sus fragmentos, ordenados.");
  process.exit(0);
}
if (process.argv.includes("--consolidate")) {
  for (const f of [CATALOG, SERVER]) { const r = consolidate(f); console.log(`${path.basename(f)}: ${r.keys} claves, ${r.fragments} fragmentos consolidados.`); }
  process.exit(0);
}
const { merged: catalog, problems } = readCatalog(CATALOG);
problems.push(...readCatalog(SERVER).problems);
const missing = [...keys].filter((k) => !(k in catalog)).sort();
const unused = Object.keys(catalog).filter((k) => !keys.has(k)).sort();
if (process.argv.includes("--list")) { console.log(JSON.stringify(Object.fromEntries(missing.map((k) => [k, ""])), null, 1)); process.exit(0); }
if (literal.length) { console.error(`Texto sin traducir en la interfaz (usa t(\"…\") o marca la línea con // i18n-ok: motivo):\n  - ${literal.slice(0, 20).join("\n  - ")}${literal.length > 20 ? "\n  …" : ""}`); }
if (literal.length || missing.length || unused.length || problems.length) {
  for (const p of problems) console.error(p.replaceAll(ROOT + path.sep, ""));
  if (missing.length) console.error(`Faltan ${missing.length} traducciones al inglés (node scripts/i18n.mjs --list):\n  - ${missing.slice(0, 15).join("\n  - ")}${missing.length > 15 ? "\n  …" : ""}`);
  if (unused.length) console.error(`Sobran ${unused.length} claves sin uso en en.json:\n  - ${unused.slice(0, 15).join("\n  - ")}`);
  process.exit(1);
}
console.log(`i18n: ${keys.size} textos, todos traducidos al inglés.`);
