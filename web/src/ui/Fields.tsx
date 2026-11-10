import { useTranslation } from "react-i18next";
import { T } from "../i18n";
import { Alert as MAlert, Autocomplete as MAutocomplete, Card as MCard, Checkbox as MCheckbox, CopyButton as MCopyButton, NumberInput as MNumberInput, PasswordInput as MPasswordInput, Radio as MRadio,
  Select as MSelect, Switch as MSwitch, Textarea as MTextarea, TextInput as MTextInput,
  type AlertProps, type AutocompleteProps, type CardProps, type CheckboxProps, type NumberInputProps, type PasswordInputProps, type RadioProps, type SelectProps, type SwitchProps, type TextareaProps, type TextInputProps } from "@mantine/core";
import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { Btn } from "./Btn";
import { Icon } from "./Icon";

const cx = (a: string, b?: string) => (b ? `${a} ${b}` : a);

/* Campos de formulario: un solo tamaño y una sola forma en toda la aplicación (el tamaño que pida un sitio de uso se ignora). */
export function TextField(p: TextInputProps) { return <MTextInput {...p} size="sm" className={cx("ms-field", p.className)} />; }
export function NumberField(p: NumberInputProps) { return <MNumberInput {...p} size="sm" className={cx("ms-field ms-field-num", p.className)} />; }
export function PasswordField(p: PasswordInputProps) { return <MPasswordInput {...p} size="sm" className={cx("ms-field", p.className)} />; }
export function TextArea(p: TextareaProps) { return <MTextarea {...p} size="sm" className={cx("ms-field", p.className)} />; }
export function SelectField(p: SelectProps) { return <MSelect {...p} size="sm" className={cx("ms-field", p.className)} />; }
export function ComboField(p: AutocompleteProps) { return <MAutocomplete {...p} size="sm" className={cx("ms-field", p.className)} />; }
export function Check(p: CheckboxProps) { return <MCheckbox {...p} size="sm" className={cx("ms-check", p.className)} />; }
export function Toggle(p: SwitchProps) { return <MSwitch {...p} size="sm" className={cx("ms-toggle-field", p.className)} />; }
/** One choice of a `RadioGroup` (pick one among several, such as which fact stays current). */
export function Radio(p: RadioProps) { return <MRadio {...p} size="sm" className={cx("ms-check", p.className)} />; }
export const RadioGroup = MRadio.Group;

/** Aviso en línea (información, atención o error), con icono. El color lo decide `tone`. */
/** `role`/`aria-label`: for a notice that is content rather than an alarm (a written answer as it streams), so a screen reader does not
 *  interrupt with every piece of it; by default it is an alert. */
export function Notice({ tone = "info", title, children, role, "aria-label": label }: { tone?: "info" | "warn" | "danger" | "success"; title?: string; children?: ReactNode; role?: string; "aria-label"?: string } & Omit<AlertProps, "color" | "title" | "children" | "icon">) {
  return (
    <MAlert className="ms-notice" data-tone={tone} title={title} role={role} aria-label={label} icon={<Icon name={tone === "info" ? "info" : tone === "success" ? "check" : "alert"} size={18} />}>{children}</MAlert>
  );
}

/** Panel: contenedor con filete, sobre la superficie. */
export function Panel({ children, className, ...rest }: CardProps & ComponentPropsWithoutRef<"div">) {
  return <MCard withBorder {...rest} className={`ms-panel${className ? ` ${className}` : ""}`}>{children}</MCard>;
}

/** Botón que copia un texto al portapapeles y avisa de que lo ha hecho. */
export function CopyBtn({ value, label = T("Copiar"), doneLabel = T("Copiado") }: { value: string; label?: string; doneLabel?: string }) {
  const { t } = useTranslation();
  return (
    <MCopyButton value={value}>
      {({ copied, copy }) => <Btn icon="copy" onClick={copy}>{t(copied ? doneLabel : label)}</Btn>}
    </MCopyButton>
  );
}

/** Error de una mutación o consulta como aviso en línea; no pinta nada si no hay error. What the server wrote for people (a 4xx, a 503
 *  saying which service does not answer) is shown as it is. A request that never reached the server, or a 500/502 (an unexpected failure,
 *  whose text is for whoever runs the instance), says in words what happened and what to do, with the server's own text folded under
 *  «Technical detail». */
export function MutationError({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!error) return null;
  const text = error instanceof Error ? error.message : String(error);
  const status = typeof error === "object" && error !== null && "status" in error ? Number((error as { status: unknown }).status) : 0;
  const offline = error instanceof TypeError;  // fetch() rejects with a TypeError when the request does not get out
  if (!offline && status !== 500 && status !== 502) return <Notice tone="danger">{text}</Notice>;
  return (
    <Notice tone="danger" title={offline ? t("No hay conexión con el servidor") : t("El servidor no ha podido hacerlo")}>
      {offline ? t("Comprueba la conexión y vuelve a intentarlo.") : t("Vuelve a intentarlo. Si se repite, avisa a quien administra la instancia con el detalle técnico.")}
      <details className="ms-errdetail"><summary>{t("Detalle técnico")}</summary><code>{text}</code></details>
    </Notice>
  );
}

/** Mensaje de «no hay nada que mostrar»: una sola forma para listas, tablas, paneles vacíos y lo que tu rol no puede ver. `action`: what
 *  to do next (a link to where things are made), after the sentence. Loading is `Loading`, not this. */
export function EmptyState({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return <div className="ms-empty">{children}{action && <span className="ms-empty-action">{action}</span>}</div>;
}

/** Estado de una consulta sin datos: cargando, o error con «Reintentar». Con datos y `children`, los pinta. */
export function DataState<T>({ query, children }: { query: { data?: T; isError: boolean; error: unknown; refetch: () => unknown }; children?: (data: T) => ReactNode }) {
  const { t } = useTranslation();
  if (query.isError && query.data === undefined) {
    return <Notice tone="danger" title={t("No se han podido cargar los datos")}>{query.error instanceof Error ? query.error.message : String(query.error)} <Btn kind="link" onClick={() => query.refetch()}>{t("Reintentar")}</Btn></Notice>;
  }
  if (query.data === undefined) return <div className="ms-empty" role="status">{t("Cargando…")}</div>;
  return <>{children?.(query.data)}</>;
}

/** Sección de una pantalla: panel con título en versalitas, contenido y una nota opcional al pie. Llena el alto de su celda en una `ColGrid`. */
export function Section({ title, hint, actions, children }: { title: string; hint?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <Panel className="ms-card">
      {actions ? <div className="ms-card-head"><div className="ms-card-title">{title}</div><div className="ms-card-actions">{actions}</div></div>
        : <div className="ms-card-title">{title}</div>}
      <div className="ms-card-body">{children}</div>
      {hint && <div className="ms-card-hint">{hint}</div>}
    </Panel>
  );
}
