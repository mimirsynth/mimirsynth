import { CopyBtn } from "./Fields";

/** Texto en monoespaciado (JSON, contexto inyectado, tokens), con ajuste de línea y, opcionalmente, botón de copiar. */
export function CodeBlock({ children, copy, select }: { children: string; copy?: boolean; select?: boolean }) {
  return (
    <div className="ms-codeblock">
      {copy && <div className="ms-codeblock-copy"><CopyBtn value={children} /></div>}
      <pre className="ms-data" data-select={select ? "" : undefined}>{children}</pre>
    </div>
  );
}
