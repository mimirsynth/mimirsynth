// Análisis de un fichero de la interfaz para i18n.mjs: las claves traducibles (t("…"), tr("…"), T("…")) y el texto visible que no pasa por ellas.
// Texto visible es el de JSX (<b>Hola</b>), el de un atributo de texto (label="Hola") y, desde #404, el que llega a uno de esos sitios como
// expresión: una plantilla (label={`Mi cuenta · ${name}`}), un literal en una condición (title={x ? "Sí" : t("No")}) o un hijo {"Hola"}.
// Lo que entra en una llamada (t(…), fmt(…), String(…)) no se mira: o es una clave o lo traduce otra función.
// Una excepción justificada se marca con `// i18n-ok: motivo` en la línea.
import { parseSync } from "oxc-parser";

export const TEXT_ATTRS = new Set(["label", "title", "description", "placeholder", "warning", "hint", "aria-label", "alt", "action", "subtitle", "tooltip"]);
const WORD = /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}/;
const PATH_OR_URL = /^\s*(\/|https?:\/\/)\S*\s*$/;  // «/sources», «https://…»: an example to type, the same in every language

const isStr = (a) => a && ((a.type === "Literal" && typeof a.value === "string") || (a.type === "TemplateLiteral" && a.expressions.length === 0));
const strOf = (a) => (a.type === "Literal" ? a.value : a.quasis[0].value.cooked);

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
    case "ParenthesizedExpression": case "TSAsExpression": case "TSNonNullExpression": shown(e.expression, out); break;
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
  const visit = (n) => {
    if (!n || typeof n.type !== "string") return;
    if (n.type === "JSXText" && WORD.test(text.slice(n.start, n.end).replace(/&[a-z]+;/g, ""))) flag(n, `texto sin traducir en JSX: ${JSON.stringify(text.slice(n.start, n.end).trim().slice(0, 50))}`);
    if (n.type === "JSXAttribute" && n.value && n.name.type === "JSXIdentifier" && TEXT_ATTRS.has(n.name.name)) {
      if (n.value.type === "Literal" && typeof n.value.value === "string" && WORD.test(n.value.value)) flag(n, `${n.name.name}="${n.value.value.slice(0, 40)}" sin traducir`);
      if (n.value.type === "JSXExpressionContainer") flagShown(n.value.expression, n.name.name);
    }
    if ((n.type === "JSXElement" || n.type === "JSXFragment") && n.children) {
      for (const c of n.children) if (c.type === "JSXExpressionContainer") flagShown(c.expression, "texto en JSX");
    }
    if (n.type === "CallExpression" && n.callee.type === "Identifier" && ["t", "tr", "T"].includes(n.callee.name) && isStr(n.arguments[0])) keys.push(strOf(n.arguments[0]));
    for (const k in n) {
      if (k === "parent") continue;
      const v = n[k];
      if (Array.isArray(v)) v.forEach(visit); else if (v && typeof v === "object") visit(v);
    }
  };
  visit(program);
  return { keys, literal };
}
