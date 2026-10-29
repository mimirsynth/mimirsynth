import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { ForceRenderer, type Effects, type EffectsMode, type RendererEvents, type RHalo, type RLink, type RNode } from "./graph/ForceRenderer";

export type { Effects, EffectsMode, RHalo as CanvasHalo, RLink as CanvasLink, RNode as CanvasNode };
export type GraphCanvasHandle = {
  /** Encuadra los nodos visibles, o solo los que cumplen `only`, con una transición de `ms` milisegundos. */
  fit: (ms?: number, only?: (id: string) => boolean) => void;
  /** PNG de lo que se ve, como data URL. */
  toPng: () => string | null;
};

/** Lienzo de grafo 2D (fuerzas): recibe nodos, aristas y halos ya decididos (color, tamaño, visibilidad, origen) y avisa de los clics.
 * Ocupa todo su contenedor y se redimensiona con él. Al pasar sobre un nodo muestra su `tooltip`; `busy` tapa el lienzo con un aviso
 * mientras se calcula. `effects` es el modo de efectos gráficos y `onEffects` recibe el modo efectivo (el automático puede bajar a reducido). */
export function GraphCanvas({ nodes, links, halos, selectedNode, selectedLink, paused, effects = "auto", busy, onEffects, onNodeClick, onNodeContextMenu, onLinkClick, onBackgroundClick, ref }: {
  nodes: RNode[]; links: RLink[]; halos?: RHalo[]; selectedNode?: string | null; selectedLink?: string | null; paused?: boolean; ref?: Ref<GraphCanvasHandle>;
  effects?: EffectsMode; busy?: string; onEffects?: (e: Effects) => void;
} & { onNodeClick?: RendererEvents["nodeClick"]; onNodeContextMenu?: RendererEvents["nodeContextMenu"]; onLinkClick?: RendererEvents["linkClick"]; onBackgroundClick?: RendererEvents["backgroundClick"] }) {
  const box = useRef<HTMLDivElement>(null);
  const cv = useRef<HTMLCanvasElement>(null);
  const r = useRef<ForceRenderer | null>(null);
  const [tip, setTip] = useState<{ id: string; x: number; y: number } | null>(null);

  useEffect(() => {
    const rr = new ForceRenderer(cv.current!);
    r.current = rr;
    const el = box.current!;
    const ro = new ResizeObserver(() => { const b = el.getBoundingClientRect(); rr.resize(Math.floor(b.width), Math.floor(b.height)); });
    ro.observe(el);
    return () => { ro.disconnect(); rr.destroy(); r.current = null; };
  }, []);
  useEffect(() => {
    r.current?.setEvents({ nodeClick: onNodeClick, nodeContextMenu: onNodeContextMenu, linkClick: onLinkClick, backgroundClick: onBackgroundClick, effects: onEffects,
      hover: (id, x, y) => setTip(id ? { id, x, y } : null) });
  }, [onNodeClick, onNodeContextMenu, onLinkClick, onBackgroundClick, onEffects]);
  useEffect(() => { r.current?.setEffects(effects); }, [effects]);
  useEffect(() => { r.current?.setData(nodes, links, halos); }, [nodes, links, halos]);
  useEffect(() => { r.current?.setSelection(selectedNode ?? null, selectedLink ?? null); }, [selectedNode, selectedLink]);
  useEffect(() => { r.current?.setPaused(!!paused); }, [paused]);
  useImperativeHandle(ref, () => ({ fit: (ms, only) => r.current?.fit(ms, only), toPng: () => r.current?.toPng() ?? null }), []);

  const tipText = tip ? nodes.find((n) => n.id === tip.id)?.tooltip : undefined;
  return (
    <div ref={box} className="ms-graph-canvas">
      <canvas ref={cv} />
      {tip && tipText && <div className="ms-graph-tip" role="tooltip" style={{ left: tip.x, top: tip.y }}>{tipText.split("\n").map((l, i) => <div key={i}>{l}</div>)}</div>}
      {busy && <div className="ms-graph-busy" role="status">{busy}</div>}
    </div>
  );
}
