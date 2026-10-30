import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { ForceRenderer } from "./graph/ForceRenderer";
import type { Layout } from "./graph/layouts";
import type { Effects, EffectsMode, GraphRenderer, RendererEvents, RHalo, RLink, RNode } from "./graph/types";

export type { Effects, EffectsMode, Layout, RHalo as CanvasHalo, RLink as CanvasLink, RNode as CanvasNode };
export type GraphCanvasHandle = {
  /** Encuadra los nodos visibles, o solo los que cumplen `only`, con una transición de `ms` milisegundos. */
  fit: (ms?: number, only?: (id: string) => boolean) => void;
  /** PNG de lo que se ve, como data URL. */
  toPng: () => string | null;
  /** Suelta los nodos fijados al arrastrarlos y recoloca el grafo. */
  resetPositions: () => void;
};

/** Lienzo de grafo, en 2D (canvas) o en 3D (WebGL): recibe nodos, aristas y halos ya decididos (color, tamaño, visibilidad, origen) y avisa de los clics.
 * `layout` es la disposición (fuerza, radial o árbol; los halos solo se dibujan en fuerza) y `root`, la raíz de radial y árbol.
 * Ocupa todo su contenedor y se redimensiona con él. Al pasar sobre un nodo muestra su `tooltip`; `busy` tapa el lienzo con un aviso
 * mientras se calcula. `effects` es el modo de efectos gráficos y `onEffects` recibe el modo efectivo (el automático puede bajar a reducido);
 * `onSlow` avisa si el 3D sigue lento incluso así. */
export function GraphCanvas({ nodes, links, halos, dim = "2d", layout = "force", root, selectedNode, selectedLink, paused, effects = "auto", busy, onEffects, onSlow, onNodeClick, onNodeContextMenu, onLinkClick, onBackgroundClick, ref }: {
  nodes: RNode[]; links: RLink[]; halos?: RHalo[]; dim?: "2d" | "3d"; layout?: Layout; root?: string; selectedNode?: string | null; selectedLink?: string | null; paused?: boolean; ref?: Ref<GraphCanvasHandle>;
  effects?: EffectsMode; busy?: string; onEffects?: (e: Effects) => void; onSlow?: () => void;
} & { onNodeClick?: RendererEvents["nodeClick"]; onNodeContextMenu?: RendererEvents["nodeContextMenu"]; onLinkClick?: RendererEvents["linkClick"]; onBackgroundClick?: RendererEvents["backgroundClick"] }) {
  const box = useRef<HTMLDivElement>(null);
  const r = useRef<GraphRenderer | null>(null);
  const [tip, setTip] = useState<{ id: string; x: number; y: number } | null>(null);
  const events = (): RendererEvents => ({ nodeClick: onNodeClick, nodeContextMenu: onNodeContextMenu, linkClick: onLinkClick, backgroundClick: onBackgroundClick, effects: onEffects, slow: onSlow,
    hover: (id, x, y) => setTip(id ? { id, x, y } : null) });
  const latest = useRef({ nodes, links, halos, layout, root, selectedNode, selectedLink, paused, effects, events });
  latest.current = { nodes, links, halos, layout, root, selectedNode, selectedLink, paused, effects, events };

  useEffect(() => {  // un lienzo por dimensión: al cambiarla se crea el otro con el estado actual. El 3D (three.js) se carga solo si se pide.
    const el = box.current!;
    let rr: GraphRenderer | null = null, ro: ResizeObserver | null = null, cv: HTMLCanvasElement | null = null, gone = false;
    const start = (make: (c: HTMLCanvasElement) => GraphRenderer) => {
      if (gone) return;
      cv = document.createElement("canvas");
      el.prepend(cv);
      const x = make(cv), p = latest.current;
      x.setEvents(p.events()); x.setEffects(p.effects); x.setLayout(p.layout, p.root); x.setPaused(!!p.paused);
      x.setData(p.nodes, p.links, p.halos); x.setSelection(p.selectedNode ?? null, p.selectedLink ?? null);
      rr = r.current = x;
      ro = new ResizeObserver(() => { const b = el.getBoundingClientRect(); x.resize(Math.floor(b.width), Math.floor(b.height)); });
      ro.observe(el);
    };
    if (dim === "3d") import("./graph/Force3DRenderer").then((m) => start((c) => new m.Force3DRenderer(c)));
    else start((c) => new ForceRenderer(c));
    return () => { gone = true; ro?.disconnect(); rr?.destroy(); cv?.remove(); r.current = null; setTip(null); };
  }, [dim]);
  useEffect(() => { r.current?.setEvents(events()); }, [onNodeClick, onNodeContextMenu, onLinkClick, onBackgroundClick, onEffects, onSlow]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { r.current?.setEffects(effects); }, [effects]);
  useEffect(() => { r.current?.setLayout(layout, root); }, [layout, root]);
  useEffect(() => { r.current?.setData(nodes, links, halos); }, [nodes, links, halos]);
  useEffect(() => { r.current?.setSelection(selectedNode ?? null, selectedLink ?? null); }, [selectedNode, selectedLink]);
  useEffect(() => { r.current?.setPaused(!!paused); }, [paused]);
  useImperativeHandle(ref, () => ({ fit: (ms, only) => r.current?.fit(ms, only), toPng: () => r.current?.toPng() ?? null, resetPositions: () => r.current?.resetPositions() }), []);

  const tipText = tip ? nodes.find((n) => n.id === tip.id)?.tooltip : undefined;
  return (
    <div ref={box} className="ms-graph-canvas">
      {tip && tipText && <div className="ms-graph-tip" role="tooltip" style={{ left: tip.x, top: tip.y }}>{tipText.split("\n").map((l, i) => <div key={i}>{l}</div>)}</div>}
      {busy && <div className="ms-graph-busy" role="status">{busy}</div>}
    </div>
  );
}
