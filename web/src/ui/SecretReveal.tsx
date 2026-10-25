import { useTranslation } from "react-i18next";
import { T } from "../i18n";
import { Btn } from "./Btn";
import { CodeBlock } from "./CodeBlock";
import { CopyBtn, Notice } from "./Fields";
import { Modal } from "./Layout";

/** Diálogo que muestra un secreto una sola vez (token nuevo): no se cierra sin pulsar el botón. */
export function SecretReveal({ value, title = T("Token creado"), note = T("Cópialo ahora: es la única vez que se muestra."), onClose }: { value: string; title?: string; note?: string; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <Modal opened={!!value} onClose={onClose} title={t(title)} withCloseButton={false} closeOnClickOutside={false} closeOnEscape={false}>
      <div className="ms-confirm">
        <Notice tone="warn">{t(note)}</Notice>
        <CodeBlock select>{value}</CodeBlock>
        <div className="ms-confirm-actions" style={{ justifyContent: "space-between" }}><CopyBtn value={value} /><Btn kind="primary" onClick={onClose}>{t("Ya lo he guardado, cerrar")}</Btn></div>
      </div>
    </Modal>
  );
}
