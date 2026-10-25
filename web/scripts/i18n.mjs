// Extrae las claves traducibles (t("…"), tr("…"), T("…")) y comprueba que el catálogo en.json las cubre todas y no tiene sobrantes.
//   node scripts/i18n.mjs          comprueba (falla si faltan o sobran claves)
//   node scripts/i18n.mjs --list   lista las claves que faltan por traducir
// Además prohíbe texto sin traducir en la interfaz: todo texto visible pasa por t()/tr()/T(). Excepción justificada: `// i18n-ok: motivo` en la línea.
import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const ROOT = new URL("../src", import.meta.url).pathname;
const files = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => e.isDirectory() ? files(path.join(d, e.name)) : /\.tsx?$/.test(e.name) ? [path.join(d, e.name)] : []);
const keys = new Set();
const literal = [];
const TEXT_ATTRS = new Set(["label", "title", "description", "placeholder", "warning", "hint", "aria-label", "alt", "action"]);
for (const f of files(ROOT)) {
  if (f.includes(`${path.sep}i18n${path.sep}`)) continue;
  const sf = ts.createSourceFile(f, fs.readFileSync(f, "utf8"), ts.ScriptTarget.Latest, true, f.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const lines = sf.text.split("\n");
  const visit = (n) => {
    const flag = (node, what) => { const ln = sf.getLineAndCharacterOfPosition(node.getStart()).line; if (!/i18n-ok/.test(lines[ln])) literal.push(`${path.relative(ROOT, f)}:${ln + 1}  ${what}`); };
    if (ts.isJsxText(n) && /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}/.test(n.getText().replace(/&[a-z]+;/g, ""))) flag(n, `texto sin traducir en JSX: ${JSON.stringify(n.getText().trim().slice(0, 50))}`);
    if (ts.isJsxAttribute(n) && n.initializer && ts.isStringLiteral(n.initializer) && TEXT_ATTRS.has(n.name.getText()) && /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}/.test(n.initializer.text)) flag(n, `${n.name.getText()}="${n.initializer.text.slice(0, 40)}" sin traducir`);
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && ["t", "tr", "T"].includes(n.expression.text)) {
      const a = n.arguments[0];
      if (a && (ts.isStringLiteral(a) || ts.isNoSubstitutionTemplateLiteral(a))) keys.add(a.text);
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
}
const catalog = JSON.parse(fs.readFileSync(path.join(ROOT, "i18n", "en.json"), "utf8"));
const missing = [...keys].filter((k) => !(k in catalog)).sort();
const unused = Object.keys(catalog).filter((k) => !keys.has(k)).sort();
if (process.argv.includes("--list")) { console.log(JSON.stringify(Object.fromEntries(missing.map((k) => [k, ""])), null, 1)); process.exit(0); }
if (literal.length) { console.error(`Texto sin traducir en la interfaz (usa t(\"…\") o marca la línea con // i18n-ok: motivo):\n  - ${literal.slice(0, 20).join("\n  - ")}${literal.length > 20 ? "\n  …" : ""}`); }
if (literal.length || missing.length || unused.length) {
  if (missing.length) console.error(`Faltan ${missing.length} traducciones al inglés (node scripts/i18n.mjs --list):\n  - ${missing.slice(0, 15).join("\n  - ")}${missing.length > 15 ? "\n  …" : ""}`);
  if (unused.length) console.error(`Sobran ${unused.length} claves sin uso en en.json:\n  - ${unused.slice(0, 15).join("\n  - ")}`);
  process.exit(1);
}
console.log(`i18n: ${keys.size} textos, todos traducidos al inglés.`);
