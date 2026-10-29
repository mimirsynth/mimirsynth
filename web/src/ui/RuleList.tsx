import { useTranslation } from "react-i18next";
import { Icon } from "./Icon";

/** Requisitos de un campo con su estado: neutros hasta que hay algo que comprobar (`checked`), luego cumplido o no. */
export function RuleList({ rules, checked }: { rules: { label: string; ok: boolean }[]; checked: boolean }) {
  const { t } = useTranslation();
  return (
    <ul className="ms-rules">
      {rules.map((r) => {
        const state = !checked ? "idle" : r.ok ? "ok" : "bad";
        return (
          <li key={r.label} data-state={state}>
            <Icon name={state === "bad" ? "close" : "check"} size={14} />{r.label}
            {checked && <span className="ms-sr">{r.ok ? t("(cumplida)") : t("(sin cumplir)")}</span>}
          </li>
        );
      })}
    </ul>
  );
}
