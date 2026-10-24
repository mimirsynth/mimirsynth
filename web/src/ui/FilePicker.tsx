import { useRef } from "react";
import { Btn } from "./Btn";
import type { IconName } from "./Icon";

/** Botón que abre el selector de ficheros del sistema. Entrega los ficheros elegidos y deja el campo listo para elegir otra vez. */
export function FilePicker({ label, icon = "upload", accept, multiple, disabled, loading, size, onFiles }:
  { label: string; icon?: IconName; accept: string; multiple?: boolean; disabled?: boolean; loading?: boolean; size?: "row"; onFiles: (files: FileList) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input ref={input} type="file" hidden accept={accept} multiple={multiple} onChange={(e) => { if (e.currentTarget.files?.length) onFiles(e.currentTarget.files); e.currentTarget.value = ""; }} />
      <Btn size={size} icon={icon} disabled={disabled} loading={loading} onClick={() => input.current?.click()}>{label}</Btn>
    </>
  );
}
