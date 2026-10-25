import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import enServer from "./en.server.json";

/** Idiomas con traducción. El idioma de origen es el español: las claves de los catálogos son los propios textos en español. */
export const LANGUAGES = [
  { code: "es", label: "Español" },
  { code: "en", label: "English" },
] as const;
export type Lang = (typeof LANGUAGES)[number]["code"];

const KEY = "ms-lang";
const supported = (l: string | null | undefined): Lang | null => (LANGUAGES.some((x) => x.code === l) ? (l as Lang) : null);

/** Idioma inicial: el último elegido en este navegador y, si no, el del navegador (null si no hay ninguno compatible). */
export function detectLanguage(): Lang | null {
  try { const saved = supported(localStorage.getItem(KEY)); if (saved) return saved; } catch { /* sin almacenamiento */ }
  for (const l of navigator.languages ?? [navigator.language]) { const s = supported(l?.slice(0, 2).toLowerCase()); if (s) return s; }
  return null;
}

/** El idioma de la instancia solo se usa si la persona no ha elegido uno ni su navegador pide uno compatible. */
export function applyInstanceDefault(lang: string | undefined): void {
  const l = supported(lang);
  let saved: string | null = null;
  try { saved = localStorage.getItem(KEY); } catch { /* sin almacenamiento */ }
  if (l && !supported(saved) && detectLanguage() === null) { void i18n.changeLanguage(l); document.documentElement.lang = l; }
}

/** Cambia el idioma de la interfaz y lo recuerda en este navegador. */
export function setLanguage(lang: Lang): void {
  try { localStorage.setItem(KEY, lang); } catch { /* sin almacenamiento */ }
  void i18n.changeLanguage(lang);
  document.documentElement.lang = lang;
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: { ...en, ...enServer } } },
  lng: detectLanguage() ?? "es",
  fallbackLng: false,          // sin traducción se muestra la clave, que es el texto en español
  keySeparator: false,         // las claves son frases: no hay jerarquía ni espacios de nombres
  nsSeparator: false,
  interpolation: { escapeValue: false },
  returnEmptyString: false,
});
document.documentElement.lang = i18n.language;

export default i18n;
/** Traducción fuera de componentes (funciones auxiliares): se evalúa al llamarla, así que respeta el idioma activo. */
export const tr = (key: string, opts?: Record<string, unknown>): string => i18n.t(key, opts) as string;
/** Marca un texto como traducible sin traducirlo aún (constantes de módulo); se traduce al pintarlo con `t(valor)`. */
export const T = <S extends string>(s: S): S => s;
/** Idioma de formato para fechas y números. */
export const locale = (): string => (i18n.language === "en" ? "en-GB" : "es-ES");

// --- Mensajes del servidor -------------------------------------------------------------------------------------
// La API responde en español. Se traducen por coincidencia exacta o, si el texto lleva valores sustituidos
// («el grafo origen 'x' no existe»), con las plantillas de en.server.json (claves con {{nombre}}).
type Tpl = { re: RegExp; names: string[]; to: string };
const templates: Tpl[] = Object.entries(enServer as Record<string, string>).filter(([k, v]) => k.includes("{{") && v).map(([k, v]) => {
  const names: string[] = [];
  const pattern = k.split(/\{\{(\w+)\}\}/).map((part, i) => { if (i % 2) { names.push(part); return "([\\s\\S]+?)"; } return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }).join("");
  return { re: new RegExp(`^${pattern}$`), names, to: v };
});

export function translateServer(msg: string): string {
  if (i18n.language === "es" || !msg) return msg;
  const exact = (enServer as Record<string, string>)[msg];
  if (exact) return exact;
  for (const t of templates) {
    const m = msg.match(t.re);
    if (m) return t.to.replace(/\{\{(\w+)\}\}/g, (_, n: string) => { const v = m[t.names.indexOf(n) + 1]; return v === undefined ? "" : translateServer(v); });
  }
  return msg;
}
