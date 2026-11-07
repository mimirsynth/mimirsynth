import { CopyBtn } from "./Fields";

/** Texto en monoespaciado (JSON, contexto inyectado, tokens), con ajuste de línea y, opcionalmente, botón de copiar.
 *  With `label` the block is a named region the keyboard can reach and scroll (a long context scrolls inside its own box). */
export function CodeBlock({ children, copy, select, label }: { children: string; copy?: boolean; select?: boolean; label?: string }) {
  return (
    <div className="ms-codeblock">
      {copy && <div className="ms-codeblock-copy"><CopyBtn value={children} /></div>}
      <pre className="ms-data" data-select={select ? "" : undefined} tabIndex={label ? 0 : undefined} role={label ? "region" : undefined} aria-label={label}>{children}</pre>
    </div>
  );
}
