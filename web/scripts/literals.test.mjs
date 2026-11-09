// The check for untranslated interface text (literals.mjs, run by npm run i18n): what it finds and what it lets through.
//   node --test scripts/
import assert from "node:assert/strict";
import test from "node:test";
import { scan } from "./literals.mjs";

const found = (src) => scan("x.tsx", src).literal.map((l) => l.replace(/^\d+\s+/, ""));

test("text in JSX and in a plain text attribute is flagged", () => {
  assert.equal(found(`const a = <p>Hola</p>;`).length, 1);
  assert.equal(found(`const a = <Btn label="Guardar" />;`).length, 1);
});

test("a template in a text attribute is flagged (the side menu's account link, #404)", () => {
  const r = found("const a = <UserCard label={`Mi cuenta · ${name}`} />;");
  assert.equal(r.length, 1);
  assert.match(r[0], /^label sin traducir: "Mi cuenta ·/);
});

test("a literal in a condition, a fallback or a concatenation is flagged, in an attribute or as a child", () => {
  assert.equal(found(`const a = <Modal title={x ? t("Editar") : "decisor"} />;`).length, 1);
  assert.equal(found(`const a = <Td>{u.user || "sistema"}</Td>;`).length, 1);
  assert.equal(found(`const a = <Pill>{on ? "activado" : "desactivado"}</Pill>;`).length, 2);
  assert.equal(found(`const a = <Pill title={"entidad · " + n} />;`).length, 1);
  assert.equal(found("const a = <Text>{total === 0 ? t(\"Sin resultados\") : `${from}–${to} de ${total}`}</Text>;").length, 1);
});

test("translated text, calls, paths, URLs and marked lines are let through", () => {
  assert.deepEqual(found("const a = <UserCard label={t(\"Mi cuenta · {{name}}\", { name })} title={`${t(\"Hola\")} · ${n}`} />;"), []);
  assert.deepEqual(found(`const a = <Td>{fmt(d.created_at, "short")}</Td>;`), []);
  assert.deepEqual(found(`const a = <TextField placeholder={base ?? "/sources"} hint={x ? "https://…" : undefined} />;`), []);
  assert.deepEqual(found(`const a = <Td>{x && "sistema"}</Td>;  // i18n-ok: test`), []);
  assert.deepEqual(found(`const a = <Pill className={on ? "is-on" : "is-off"}>{n}</Pill>;`), []);
});

test("the keys of t(), tr() and T() are collected", () => {
  assert.deepEqual(scan("x.ts", `t("Uno"); tr("Dos"); T(\`Tres\`); other("Cuatro");`).keys, ["Uno", "Dos", "Tres"]);
});
