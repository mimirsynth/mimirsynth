import { SelectField } from "./Fields";
import { LANGUAGES, type Lang } from "../i18n";

/** Selector de idioma de la interfaz. */
export function LanguageSelect({ value, onChange, label, size }: { value: string; onChange: (lang: Lang) => void; label?: string; size?: "xs" | "sm" }) {
  return (
    <SelectField label={label} aria-label={label ?? "Language"} /* i18n-ok: the language picker is named in English so anyone can find it */ size={size} w={170} allowDeselect={false} value={value}
      data={LANGUAGES.map((l) => ({ value: l.code, label: l.label }))} onChange={(v) => v && onChange(v as Lang)} />
  );
}
