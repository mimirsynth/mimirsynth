import { Btn } from "./Btn";
import { CodeBlock } from "./CodeBlock";
import { CopyBtn, Notice } from "./Fields";
import { Modal } from "./Layout";

/** Diálogo que muestra un secreto una sola vez (token nuevo): no se cierra sin pulsar el botón. */
export function SecretReveal({ value, title = "Token creado", note = "Cópialo ahora: es la única vez que se muestra.", onClose }: { value: string; title?: string; note?: string; onClose: () => void }) {
  return (
    <Modal opened={!!value} onClose={onClose} title={title} withCloseButton={false} closeOnClickOutside={false} closeOnEscape={false}>
      <div className="ms-confirm">
        <Notice tone="warn">{note}</Notice>
        <CodeBlock select>{value}</CodeBlock>
        <div className="ms-confirm-actions" style={{ justifyContent: "space-between" }}><CopyBtn value={value} /><Btn kind="primary" onClick={onClose}>Ya lo he guardado, cerrar</Btn></div>
      </div>
    </Modal>
  );
}
