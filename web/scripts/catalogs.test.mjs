// Translation catalogues in fragments: reading, the checks that reject a clash or an unsorted file, and the consolidation at release.
//   node --test scripts/
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { consolidate, readCatalog, sortCatalog } from "./catalogs.mjs";

const json = (o) => JSON.stringify(o, null, 1) + "\n";

function fixture(files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "i18n-"));
  for (const [name, body] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(dir, name)), { recursive: true });
    fs.writeFileSync(path.join(dir, name), typeof body === "string" ? body : json(body));
  }
  return path.join(dir, "en.json");
}

test("the catalogue and its fragments are read as one", () => {
  const file = fixture({ "en.json": { Adiós: "Bye", Hola: "Hello" }, "en/a.json": { Casa: "House" }, "en/b.json": { Perro: "Dog", Árbol: "Tree" }, "en/README.md": "# notes" });
  const r = readCatalog(file);
  assert.deepEqual(r.problems, []);
  assert.deepEqual(r.merged, { Adiós: "Bye", Hola: "Hello", Casa: "House", Perro: "Dog", Árbol: "Tree" });
  assert.equal(r.files.length, 3);
});

test("a key in two files and an unsorted fragment are rejected", () => {
  const file = fixture({ "en.json": { Hola: "Hello" }, "en/a.json": { Hola: "Hi" }, "en/b.json": { Zeta: "Z", Alfa: "A" } });
  const { problems } = readCatalog(file);
  assert.equal(problems.length, 2);
  assert.match(problems.find((p) => p.startsWith("la clave")), /"Hola".*en\.json.*a\.json/);
  assert.match(problems.find((p) => p.includes("orden")), /b\.json/);
  assert.throws(() => consolidate(file), /la clave "Hola"/);   // nothing is merged while two files disagree
  assert.ok(fs.existsSync(path.join(path.dirname(file), "en", "a.json")));
});

test("--sort puts every file in order", () => {
  const file = fixture({ "en.json": { b: "B", a: "A" }, "en/x.json": { d: "D", c: "C" } });
  sortCatalog(file);
  assert.deepEqual(readCatalog(file).problems, []);
});

test("consolidating gives the sorted catalogue adding the keys by hand would, and removes the fragments", () => {
  const base = { Adiós: "Bye", Hola: "Hello", "Sin {{n}}": "No {{n}}" };
  const added = { Casa: "House", Árbol: "Tree", "Ver {{n}}": "View {{n}}", Perro: "Dog" };
  const file = fixture({ "en.json": base, "en/a.json": { Casa: "House", "Ver {{n}}": "View {{n}}" }, "en/b.json": { Perro: "Dog", Árbol: "Tree" }, "en/README.md": "# notes" });
  const byHand = Object.fromEntries(Object.keys({ ...base, ...added }).sort().map((k) => [k, { ...base, ...added }[k]]));
  assert.deepEqual(consolidate(file), { keys: 7, fragments: 2 });
  assert.equal(fs.readFileSync(file, "utf8"), json(byHand));
  assert.deepEqual(fs.readdirSync(path.join(path.dirname(file), "en")), ["README.md"]);
});

test("a catalogue written with CRLF keeps its line endings", () => {
  const file = fixture({ "en.json": '{\r\n "a": "A"\r\n}\r\n', "en/x.json": { b: "B" } });
  consolidate(file);
  assert.equal(fs.readFileSync(file, "utf8"), '{\r\n "a": "A",\r\n "b": "B"\r\n}\r\n');
});
