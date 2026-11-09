// Análisis de un fichero de la interfaz para i18n.mjs: las claves traducibles (t("…"), tr("…"), T("…")) y el texto visible que no pasa por ellas.
// Texto visible es el de JSX (<b>Hola</b>), el de un atributo de texto (label="Hola") y, desde #404, el que llega a uno de esos sitios como
// expresión: una plantilla (label={`Mi cuenta · ${name}`}), un literal en una condición (title={x ? "Sí" : t("No")}) o un hijo {"Hola"}.
// Lo que entra en una llamada (t(…), fmt(…), String(…)) no se mira: o es una clave o lo traduce otra función.
// Desde #421 mira además lo que llega al texto sin pasar por un atributo de texto: una propiedad de texto de un objeto escrito dentro de
// un atributo (series={[{ name: "Episodios" }]}), la búsqueda en un objeto escrito en el JSX ({{ active: "indexados" }[k]}) y las tablas
// del módulo que se traducen al usarlas, t(LABEL[estado]): sus textos van en T("…"), si no, ni se extraen ni se traducen.
// Una excepción justificada se marca con `// i18n-ok: motivo` en la línea.
import { parseSync } from "oxc-parser";

export const TEXT_ATTRS = new Set(["label", "title", "description", "placeholder", "warning", "hint", "aria-label", "alt", "action", "subtitle", "tooltip", "center", "empty"]);
// Properties that carry text in an object written in an attribute (a chart's series, a list's items) or in a table of the module.
export const TEXT_KEYS = new Set(["label", "name", "title", "text", "description", "hint", "help", "placeholder", "unit", "empty", "center"]);
const WORD = /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}/;
const PATH_OR_URL = /^\s*(\/|https?:\/\/)\S*\s*$/;  // «/sources», «https://…»: an example to type, the same in every language

const isStr = (a) => a && ((a.type === "Literal" && typeof a.value === "string") || (a.type === "TemplateLiteral" && a.expressions.length === 0));
const strOf = (a) => (a.type === "Literal" ? a.value : a.quasis[0].value.cooked);

const unwrap = (e) => (["ParenthesizedExpression", "TSAsExpression", "TSSatisfiesExpression", "TSNonNullExpression"].includes(e?.type) ? unwrap(e.expression) : e);
const keyOf = (p) => (p.type === "Property" && !p.computed ? p.key.name ?? p.key.value : undefined);

// The identifier an expression starts from: LABEL in LABEL[x] ?? x, ROLES.find(…)?.label, SEVERITY[s].label.
function rootOf(e) {
  e = unwrap(e);
  if (!e) return undefined;
  if (e.type === "Identifier") return e.name;
  if (e.type === "LogicalExpression") return rootOf(e.left);
  if (e.type === "ChainExpression") return rootOf(e.expression);
  if (e.type === "MemberExpression") return rootOf(e.object);
  if (e.type === "CallExpression") return rootOf(e.callee);
  return undefined;
}

// The texts of a table that a call t(TABLE[…]) translates: every value of a flat table of strings ({ failed: "fallida" }) and, deeper, the
// values of the properties that carry text ({ key, label: "…" }). Keys, routes and colours are left alone.
function tableTexts(e, out = [], flat = true) {
  e = unwrap(e);
  if (!e) return out;
  if (e.type === "ArrayExpression") e.elements.forEach((x) => tableTexts(x, out, false));
  if (e.type === "ObjectExpression") {
    for (const p of e.properties) {
      if (p.type !== "Property") continue;
      const v = unwrap(p.value);
      if (v.type === "ObjectExpression" || v.type === "ArrayExpression") tableTexts(v, out, false);
      else if (flat || TEXT_KEYS.has(keyOf(p))) shown(v, out);
    }
  }
  return out;
}

// The string pieces an expression shows as they are: those of a literal or a template, through conditions, ||/?? and concatenations.
function shown(e, out = []) {
  if (!e) return out;
  switch (e.type) {
    case "Literal": if (typeof e.value === "string") out.push({ node: e, text: e.value }); break;
    case "TemplateLiteral": {
      const text = e.quasis.map((q) => q.value.cooked ?? "").join(" ");
      if (WORD.test(text)) out.push({ node: e, text });
      e.expressions.forEach((x) => shown(x, out));
      break;
    }
    case "ConditionalExpression": shown(e.consequent, out); shown(e.alternate, out); break;
    case "LogicalExpression": if (e.operator !== "&&") shown(e.left, out); shown(e.right, out); break;
    case "BinaryExpression": if (e.operator === "+") { shown(e.left, out); shown(e.right, out); } break;
    case "ParenthesizedExpression": case "TSAsExpression": case "TSSatisfiesExpression": case "TSNonNullExpression": shown(e.expression, out); break;
    case "MemberExpression": {   // ({ active: "indexados", error: t("con error") } as Record<string, string>)[k]
      const o = unwrap(e.object);
      if (o.type === "ObjectExpression") o.properties.forEach((p) => p.type === "Property" && shown(p.value, out));
      break;
    }
  }
  return out;
}

export function scan(file, text) {
  const keys = [];
  const literal = [];
  const { program, errors } = parseSync(file, text, { lang: file.endsWith("x") ? "tsx" : "ts" });
  if (errors.length) return { keys, literal: [`no se pudo analizar: ${errors[0].message}`] };
  const lines = text.split("\n");
  const lineOf = (pos) => text.slice(0, pos).split("\n").length - 1;
  const flag = (node, what) => { const ln = lineOf(node.start); if (!/i18n-ok/.test(lines[ln])) literal.push(`${ln + 1}  ${what}`); };
  const flagShown = (expr, where) => {
    for (const s of shown(expr)) if (WORD.test(s.text) && !PATH_OR_URL.test(s.text)) flag(s.node, `${where} sin traducir: ${JSON.stringify(s.text.trim().slice(0, 50))}`);
  };
  // The tables of the module (const X = {…} or […] at the top level), to check the ones a call t(X[…]) translates.
  const tables = new Map();
  for (const st of program.body) {
    const d = st.type === "ExportNamedDeclaration" ? st.declaration : st;
    if (d?.type !== "VariableDeclaration") continue;
    for (const v of d.declarations) if (v.id.type === "Identifier" && ["ObjectExpression", "ArrayExpression"].includes(unwrap(v.init)?.type)) tables.set(v.id.name, v.init);
  }
  const checked = new Set();
  const flagTable = (name) => {
    if (checked.has(name) || !tables.has(name)) return;
    checked.add(name);
    for (const s of tableTexts(tables.get(name))) if (WORD.test(s.text) && !PATH_OR_URL.test(s.text)) flag(s.node, `${name}, traducida con t(), tiene un texto sin T(): ${JSON.stringify(s.text.trim().slice(0, 50))}`);
  };
  // In an object written in an attribute, the properties that carry text: series={[{ name: "Episodios", values }]}.
  const flagObjects = (e) => {
    e = unwrap(e);
    if (!e) return;
    if (e.type === "ArrayExpression") e.elements.forEach(flagObjects);
    if (e.type === "ConditionalExpression") { flagObjects(e.consequent); flagObjects(e.alternate); }
    if (e.type === "LogicalExpression") flagObjects(e.right);
    if (e.type === "SpreadElement") flagObjects(e.argument);
    if (e.type === "ObjectExpression") {
      for (const p of e.properties) {
        if (p.type === "SpreadElement") flagObjects(p.argument);
        else if (TEXT_KEYS.has(keyOf(p))) flagShown(p.value, `${keyOf(p)}`);
        else if (p.type === "Property") flagObjects(p.value);
      }
    }
  };
  const visit = (n) => {
    if (!n || typeof n.type !== "string") return;
    if (n.type === "JSXText" && WORD.test(text.slice(n.start, n.end).replace(/&[a-z]+;/g, ""))) flag(n, `texto sin traducir en JSX: ${JSON.stringify(text.slice(n.start, n.end).trim().slice(0, 50))}`);
    if (n.type === "JSXAttribute" && n.value && n.name.type === "JSXIdentifier" && TEXT_ATTRS.has(n.name.name)) {
      if (n.value.type === "Literal" && typeof n.value.value === "string" && WORD.test(n.value.value)) flag(n, `${n.name.name}="${n.value.value.slice(0, 40)}" sin traducir`);
      if (n.value.type === "JSXExpressionContainer") flagShown(n.value.expression, n.name.name);
    }
    if (n.type === "JSXAttribute" && n.value?.type === "JSXExpressionContainer") flagObjects(n.value.expression);
    if ((n.type === "JSXElement" || n.type === "JSXFragment") && n.children) {
      for (const c of n.children) if (c.type === "JSXExpressionContainer") flagShown(c.expression, "texto en JSX");
    }
    if (n.type === "CallExpression" && n.callee.type === "Identifier" && ["t", "tr", "T"].includes(n.callee.name) && isStr(n.arguments[0])) keys.push(strOf(n.arguments[0]));
    if (n.type === "CallExpression" && n.callee.type === "Identifier" && ["t", "tr"].includes(n.callee.name) && n.arguments[0] && !isStr(n.arguments[0])) flagTable(rootOf(n.arguments[0]));
    for (const k in n) {
      if (k === "parent") continue;
      const v = n[k];
      if (Array.isArray(v)) v.forEach(visit); else if (v && typeof v === "object") visit(v);
    }
  };
  visit(program);
  return { keys, literal };
}
