import { tr } from "./i18n";

// Espejo en el cliente de `passwords.check_policy` (api/mimirsynth/passwords.py): enseña las reglas antes de enviar (#76).
// El servidor sigue siendo quien decide; si se cambia una regla allí, hay que cambiarla aquí.
const COMMON = new Set(["password", "contraseña", "contrasena", "123456789012", "qwertyuiopas", "mimirsynth", "administrador", "letmein", "welcome"]);

const ALPHABETS = ["0123456789", "abcdefghijklmnopqrstuvwxyz"];

/** Escalera de caracteres consecutivos; en dígitos y letras puede dar la vuelta (…8901…, …yzab…). */
function isSequence(low: string) {
  if (low.length < 6) return false;
  const d = new Set<number>();
  for (let i = 0; i < low.length - 1; i++) d.add(low.charCodeAt(i + 1) - low.charCodeAt(i));
  if (d.size === 1 && (d.has(1) || d.has(-1))) return true;
  const alpha = ALPHABETS.find((a) => [...low].every((c) => a.includes(c)));
  if (!alpha) return false;
  const n = alpha.length; const w = new Set<number>();
  for (let i = 0; i < low.length - 1; i++) w.add((alpha.indexOf(low[i + 1]) - alpha.indexOf(low[i]) + n) % n);
  return w.size === 1 && (w.has(1) || w.has(n - 1));
}

export type Rule = { label: string; ok: boolean };

/** Reglas de la contraseña y si `pw` cumple cada una. La de email y nombre solo aparece si hay alguno que comprobar. */
export function passwordRules(pw: string, { min, email = "", name = "" }: { min: number; email?: string; name?: string }): Rule[] {
  const low = pw.toLowerCase();
  const local = email.split("@")[0].toLowerCase();
  const personal = [local.length >= 4 ? local : "", name.length >= 4 ? name.toLowerCase() : ""].filter(Boolean);
  const rules: Rule[] = [{ label: tr("Al menos {{min}} caracteres", { min }), ok: pw.length >= min }];
  if (personal.length) rules.push({ label: tr("Sin tu email ni tu nombre"), ok: !personal.some((p) => low.includes(p)) });
  rules.push({ label: tr("Ni común ni una secuencia (abcdef, 123456…)"), ok: pw !== "" && !COMMON.has(low) && !/^(.)\1+$/.test(pw) && !isSequence(low) });
  rules.push({ label: tr("Al menos 5 caracteres distintos"), ok: new Set(pw).size >= 5 });
  return rules;
}
