import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type Simulation, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";
import { polygonHull } from "d3-polygon";
import { quadtree } from "d3-quadtree";
import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from "d3-zoom";
import { CANVAS } from "../palette";
import { anchorOrder, hash, placeLayout, type Layout } from "./layouts";
import { CHARGE, CHARGE_WITH_HALOS, DIM, ease, ENTER_MS, FADE_MS, FOCUS_DELAY, FOLLOW_MS, LINK, LINK_WITH_HALOS, MAX_LABELS, MAX_LABELS_REDUCED, MORPH_MS, PARTICLE_MS, PULL, PULL_NONE, SLOW_FRAMES, SLOW_MS,
  type Effects, type EffectsMode, type GraphRenderer, type RendererEvents, type RHalo, type RLink, type RNode } from "./types";

export type { Effects, EffectsMode, RendererEvents, RHalo, RLink, RNode };

// ancla: media de las de sus halos; `lit`: 1 a plena luz, 0 atenuado por el foco (se acerca a su destino con un fundido); `pinned`: fijado al arrastrarlo
type SNode = RNode & SimulationNodeDatum & { ax?: number; ay?: number; pull?: number; lit?: number; pinned?: boolean };
type SLink = Omit<RLink, "source" | "target"> & SimulationLinkDatum<SNode> & { source: SNode; target: SNode; bend: number; lit?: number };

const FONT = "11px system-ui, -apple-system, 'Segoe UI', sans-serif";
const SETTLE_MS = 400;           // presupuesto para pre-asentar un grafo nuevo antes de pintarlo
const LABEL_ZOOM = 0.7;          // por debajo, las etiquetas de las aristas no se leen y solo ensucian
const CAPTION_ZOOM = 0.45;
const CLICK_SLOP = 4;            // píxeles que puede moverse el puntero y seguir siendo un clic
const MINIMAP_MIN = 60;          // nodos visibles a partir de los que se muestra el minimapa
const MINI_W = 150;
const MINI_H = 110;
const HALO_PAD = 26;             // margen del halo alrededor de cada nodo

function seed(n: SNode) {
  const a = hash(n.id) * Math.PI * 2, r = 40 + hash(n.id + "r") * 260;
  n.x = Math.cos(a) * r; n.y = Math.sin(a) * r;
}

/** Punto de control de una arista curva: varias aristas entre los mismos nodos se separan en abanico. */
function control(l: SLink): [number, number] {
  const sx = l.source.x!, sy = l.source.y!, tx = l.target.x!, ty = l.target.y!;
  const mx = (sx + tx) / 2, my = (sy + ty) / 2;
  if (!l.bend) return [mx, my];
  const dx = tx - sx, dy = ty - sy;
  return [mx - dy * l.bend, my + dx * l.bend];
}

function distToSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number) {
  const dx = bx - ax, dy = by - ay, len = dx * dx + dy * dy;
  const t = len ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len)) : 0;
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

/** Grafo de fuerzas sobre canvas 2D: d3-force para colocar, d3-zoom para mover y ampliar, quadtree para saber qué hay bajo el puntero. */
export class ForceRenderer implements GraphRenderer {
  private ctx: CanvasRenderingContext2D;
  private nodes: SNode[] = [];
  private links: SLink[] = [];
  private byId = new Map<string, SNode>();
  private sim: Simulation<SNode, SLink>;
  private zoomer: ZoomBehavior<HTMLCanvasElement, unknown>;
  private t: ZoomTransform = zoomIdentity;
  private w = 0;
  private h = 0;
  private dpr = 1;
  private frame = 0;
  private paused = false;
  private selectedNode: string | null = null;
  private selectedLink: string | null = null;
  private hover: string | null = null;
  private focusHover: string | null = null;  // nodo señalado que ya hace de foco: el ratón se quedó FOCUS_DELAY sobre él
  private focusTimer = 0;
  private fadeAt = 0;                        // último paso de los fundidos del foco
  private haloLit = 1;
  private drag: { node: SNode; x0: number; y0: number; moved: boolean } | null = null;
  private down: { x: number; y: number } | null = null;
  private anim = 0;
  private pendingFit: (() => void) | null = null;  // encuadre pedido antes de conocer el tamaño del lienzo
  private cleanup: (() => void)[] = [];
  private halos: RHalo[] = [];
  private anchorSig = "";
  private mode: EffectsMode = "auto";
  private effective: Effects = "full";
  private autoDown = false;     // el modo automático ya bajó a reducido en este lienzo
  private still: boolean;       // prefers-reduced-motion: nada se mueve solo (ni entrada, ni partículas, ni simulación ni zoom animados), sea cual sea el modo
  private born = new Map<string, number>();  // inicio de la entrada animada de cada nodo nuevo
  private lastDraw = 0;
  private slow = 0;
  private mini: { x: number; y: number; ox: number; oy: number; s: number } | null = null;
  private layout: Layout = "force";
  private root: string | undefined;
  private morph: { from: Map<string, [number, number]>; start: number } | null = null;

  constructor(private canvas: HTMLCanvasElement, private events: RendererEvents = {}) {
    this.ctx = canvas.getContext("2d")!;
    this.still = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.sim = forceSimulation<SNode, SLink>()
      .force("link", forceLink<SNode, SLink>().id((d) => d.id).distance(70).strength(LINK))
      .force("charge", forceManyBody<SNode>().strength(CHARGE).distanceMax(600))
      .force("collide", forceCollide<SNode>((d) => d.size + 4))
      .force("x", forceX<SNode>((d) => d.ax ?? 0).strength((d) => d.pull ?? PULL_NONE))
      .force("y", forceY<SNode>((d) => d.ay ?? 0).strength((d) => d.pull ?? PULL_NONE))
      .on("tick", () => this.request())
      .stop();
    this.zoomer = zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.05, 8])
      .filter((ev: any) => (ev.type === "wheel" || (!this.nodeAt(ev.offsetX, ev.offsetY) && !this.inMini(ev.offsetX, ev.offsetY))) && !ev.button)
      .on("zoom", (ev) => { if (ev.sourceEvent) cancelAnimationFrame(this.anim); this.t = ev.transform; this.request(); });  // el usuario manda sobre un encuadre en curso
    select(canvas).call(this.zoomer).on("dblclick.zoom", null);
    const on = <K extends keyof HTMLElementEventMap>(type: K, fn: (ev: HTMLElementEventMap[K]) => void) => {
      canvas.addEventListener(type, fn as EventListener);
      this.cleanup.push(() => canvas.removeEventListener(type, fn as EventListener));
    };
    on("pointerdown", (ev) => this.onDown(ev));
    on("pointermove", (ev) => this.onMove(ev));
    on("pointerup", (ev) => this.onUp(ev));
    on("pointerleave", () => { this.aim(null); if (this.hover) { this.hover = null; this.canvas.style.cursor = ""; this.events.hover?.(null, 0, 0); this.request(); } });
    on("dblclick", (ev) => { const n = this.nodeAt(ev.offsetX, ev.offsetY); if (n?.pinned) this.unpin([n]); });
    on("pointercancel", () => this.endDrag());  // sin esto, un arrastre cancelado dejaría la simulación caliente para siempre
    on("lostpointercapture", () => this.endDrag());
    on("contextmenu", (ev) => {
      const n = this.nodeAt(ev.offsetX, ev.offsetY);
      if (n) { ev.preventDefault(); this.events.nodeContextMenu?.(n.id); }
    });
  }

  setEvents(events: RendererEvents) { this.events = events; }

  /** Modo elegido. Elegirlo de nuevo olvida una bajada automática anterior. */
  setEffects(mode: EffectsMode) {
    this.mode = mode; this.autoDown = false; this.slow = 0;
    this.applyEffects();
  }

  private applyEffects() {
    const e: Effects = this.mode === "reduced" || (this.mode === "auto" && this.autoDown) ? "reduced" : "full";
    if (e !== this.effective) { this.effective = e; this.request(); }
    this.events.effects?.(e);
  }

  resize(w: number, h: number) {
    const dpr = window.devicePixelRatio || 1;
    if (w === this.w && h === this.h && dpr === this.dpr) return;
    this.dpr = dpr;
    const first = !this.w;
    this.w = w; this.h = h;
    this.canvas.width = Math.max(1, Math.floor(w * this.dpr));
    this.canvas.height = Math.max(1, Math.floor(h * this.dpr));
    this.canvas.style.width = `${w}px`; this.canvas.style.height = `${h}px`;
    if (first) { const f = this.pendingFit ?? (() => this.fit(0)); this.pendingFit = null; if (this.nodes.length) f(); }
    this.request();
  }

  /** Datos nuevos. Conserva la posición de los nodos que ya estaban; si cambia la topología, recoloca:
   * un grafo nuevo se asienta antes de pintarlo y una expansión crece animada desde el nodo vecino. */
  setData(nodes: RNode[], links: RLink[], halos: RHalo[] = []) {
    const old = this.byId;
    this.halos = halos;
    const kept = nodes.filter((n) => old.has(n.id)).length;
    const sameTopo = kept === nodes.length && kept === old.size && links.length === this.links.length && links.every((l, i) => this.links[i]?.id === l.id);
    this.byId = new Map();
    this.nodes = nodes.map((n) => {
      const s = Object.assign(old.get(n.id) ?? ({} as SNode), n);
      this.byId.set(n.id, s);
      return s;
    });
    const pairs = new Map<string, number>();
    this.links = links.filter((l) => this.byId.has(l.source) && this.byId.has(l.target)).map((l) => {
      const key = l.source < l.target ? `${l.source}|${l.target}` : `${l.target}|${l.source}`;
      const i = pairs.get(key) ?? 0;
      pairs.set(key, i + 1);
      const dir = l.source < l.target ? 1 : -1;  // misma curva vista desde ambos extremos
      return { ...l, source: this.byId.get(l.source)!, target: this.byId.get(l.target)!, bend: i ? dir * Math.ceil(i / 2) * (i % 2 ? 0.18 : -0.18) : 0 };
    });
    const reanchor = this.anchor();
    if (sameTopo && this.layout !== "force") { this.request(); return; }
    if (sameTopo) {
      if (reanchor && this.still) this.settle(0.5);
      else if (reanchor && !this.paused) this.sim.alpha(Math.max(this.sim.alpha(), 0.5)).restart();  // otros halos: los nodos se recolocan animados
      this.request();
      return;
    }
    const fresh = this.nodes.filter((n) => n.x === undefined);
    const now = performance.now();
    for (const id of this.born.keys()) if (!this.byId.has(id)) this.born.delete(id);
    if (this.effective === "full" && !this.still) for (const n of fresh) this.born.set(n.id, now);
    for (const n of fresh) {
      const nb = this.links.find((l) => (l.source === n && l.target.x !== undefined) || (l.target === n && l.source.x !== undefined));
      const anchor = nb ? (nb.source === n ? nb.target : nb.source) : null;
      if (anchor) { n.x = anchor.x! + (hash(n.id) - 0.5) * 60; n.y = anchor.y! + (hash(n.id + "y") - 0.5) * 60; } else seed(n);
    }
    this.sim.nodes(this.nodes);
    (this.sim.force("link") as any).links(this.links);
    if (this.layout !== "force") {  // radial y árbol: posiciones calculadas, sin simulación; lo nuevo sale de su vecino
      this.place(kept > 0);
      if (!kept) this.fit(0);
      return;
    }
    if (!kept || this.still) {  // un grafo nuevo (o cualquiera, sin movimiento) se asienta antes de pintarlo
      this.settle(kept ? 0.4 : 1);
      if (!kept) this.fit(0);
    }
    if (!this.still) { this.sim.alpha(kept ? 0.4 : this.sim.alpha()); if (!this.paused) this.sim.restart(); }
    this.request();
  }

  /** Pasos síncronos de la simulación, con un presupuesto de tiempo. */
  private settle(alpha: number) {
    this.sim.stop().alpha(alpha);
    const end = performance.now() + (this.still ? SETTLE_MS * 3 : SETTLE_MS);
    while (this.sim.alpha() > this.sim.alphaMin() && performance.now() < end) this.sim.tick();
  }

  /** Coloca un ancla por halo y da a cada nodo como destino la media de las anclas de sus halos: un nodo de dos orígenes
   * queda entre ambos, en la intersección. Los halos que comparten más nodos van contiguos en el círculo. Los nodos sin
   * halo van a una zona neutra debajo. Devuelve si algo cambió (para recolocar). */
  private anchor(): boolean {
    const keys = this.halos.map((h) => h.key);
    const sig = keys.join("|") + "#" + this.nodes.map((n) => (n.groups ?? []).join(",")).join(";");
    if (sig === this.anchorSig) return false;
    this.anchorSig = sig;
    const pos = new Map<string, [number, number]>();
    if (keys.length) {
      const order = anchorOrder(this.nodes, keys);
      const r = order.length === 1 ? 0 : 120 + 30 * Math.sqrt(this.nodes.length);
      order.forEach((k, i) => { const a = -Math.PI / 2 + (i * 2 * Math.PI) / order.length; pos.set(k, [Math.cos(a) * r, Math.sin(a) * r]); });
      const neutral: [number, number] = [0, r + 180];
      for (const n of this.nodes) {
        const ps = (n.groups ?? []).map((k) => pos.get(k)).filter((q): q is [number, number] => !!q);
        if (ps.length) { n.ax = ps.reduce((a, q) => a + q[0], 0) / ps.length; n.ay = ps.reduce((a, q) => a + q[1], 0) / ps.length; n.pull = PULL; }
        else { [n.ax, n.ay] = neutral; n.pull = PULL_NONE * 2; }
      }
    } else for (const n of this.nodes) { n.ax = 0; n.ay = 0; n.pull = PULL_NONE; }
    (this.sim.force("link") as any).strength(keys.length ? LINK_WITH_HALOS : LINK);  // con halos manda el origen: las aristas tiran menos
    (this.sim.force("charge") as any).strength(keys.length ? CHARGE_WITH_HALOS : CHARGE);
    (this.sim.force("x") as any).x((d: SNode) => d.ax ?? 0);  // reinicializa los destinos
    (this.sim.force("y") as any).y((d: SNode) => d.ay ?? 0);
    return true;
  }

  /** Disposición: fuerza (simulación con anclas por origen) o radial / árbol (posiciones calculadas). `root` fija la raíz de las dos últimas. */
  setLayout(layout: Layout, root?: string) {
    if (layout === this.layout && root === this.root) return;
    const was = this.layout;
    this.layout = layout; this.root = root;
    if (!this.nodes.length) return;
    if (layout === "force") {
      for (const n of this.nodes) { n.fx = null; n.fy = null; n.pinned = false; }
      if (this.still) this.settle(0.6); else if (!this.paused) this.sim.alpha(0.6).restart();
    } else this.place(true);
    if (was !== layout) this.fit(this.still ? 0 : MORPH_MS + 200);
  }

  /** Radial o árbol: fija cada nodo en su sitio; si `animate`, viaja desde donde estaba. */
  private place(animate: boolean) {
    this.sim.stop().alpha(0);
    const pos = placeLayout(this.layout, this.nodes, this.links.map((l) => ({ source: l.source.id, target: l.target.id })), this.root);
    const from = new Map<string, [number, number]>();
    for (const n of this.nodes) {
      const p = pos.get(n.id)!;
      if (n.x !== undefined) from.set(n.id, [n.x, n.y!]);
      n.fx = p.x; n.fy = p.y; n.vx = 0; n.vy = 0; n.pinned = false;
      if (n.x === undefined || !animate || this.still) { n.x = p.x; n.y = p.y; }
    }
    this.morph = animate && !this.still ? { from, start: performance.now() } : null;
    this.request();
  }

  /** Algo se está moviendo (simulación o cambio de disposición): un encuadre en curso lo sigue. */
  private moving() { return this.layout === "force" ? !this.paused && this.sim.alpha() > 0.03 : !!this.morph; }

  setSelection(node: string | null, link: string | null) {
    if (node === this.selectedNode && link === this.selectedLink) return;
    this.selectedNode = node; this.selectedLink = link; this.request();
  }

  setPaused(p: boolean) {
    this.paused = p;
    if (this.layout !== "force") return;
    if (p || this.still) this.sim.stop(); else this.sim.alpha(Math.max(this.sim.alpha(), 0.1)).restart();
  }

  /** Encuadra los nodos visibles (o los que cumplen `only`) con una transición de `ms` milisegundos.
   * El destino se recalcula en cada paso: si la simulación sigue moviendo los nodos, el encuadre los sigue. */
  fit(ms = 400, only?: (id: string) => boolean) {
    const ns = this.nodes.filter((n) => n.visible && n.x !== undefined && (!only || only(n.id)));
    if (!ns.length) return;
    if (!this.w) { this.pendingFit = () => this.fit(0, only); return; }
    this.animateTo(() => {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const n of ns) { x0 = Math.min(x0, n.x! - n.size); y0 = Math.min(y0, n.y! - n.size); x1 = Math.max(x1, n.x! + n.size); y1 = Math.max(y1, n.y! + n.size); }
      const pad = this.halos.length ? 64 : 40, k = Math.min(only ? 2 : 1.5, (this.w - pad * 2) / Math.max(x1 - x0, 1), (this.h - pad * 2) / Math.max(y1 - y0, 1));
      return zoomIdentity.translate(this.w / 2 - k * (x0 + x1) / 2, this.h / 2 - k * (y0 + y1) / 2).scale(k);
    }, ms);
  }

  /** La imagen tal como se ve (fondo incluido). */
  toPng(): string { this.draw(); return this.canvas.toDataURL("image/png"); }

  destroy() {
    this.sim.stop();
    clearTimeout(this.focusTimer);
    cancelAnimationFrame(this.frame); cancelAnimationFrame(this.anim);
    select(this.canvas).on(".zoom", null);
    this.cleanup.forEach((f) => f());
  }

  // --- interacción ---------------------------------------------------------------------------
  private toWorld(x: number, y: number): [number, number] { return this.t.invert([x, y]); }

  private nodeAt(x: number, y: number): SNode | undefined {
    const [wx, wy] = this.toWorld(x, y);
    const vis = this.nodes.filter((n) => n.visible && n.x !== undefined);
    const qt = quadtree<SNode>().x((n) => n.x!).y((n) => n.y!).addAll(vis);
    const n = qt.find(wx, wy, 30);
    return n && Math.hypot(n.x! - wx, n.y! - wy) <= n.size + 3 / this.t.k ? n : undefined;
  }

  private linkAt(x: number, y: number): SLink | undefined {
    const [wx, wy] = this.toWorld(x, y);
    const tol = 5 / this.t.k;
    let best: SLink | undefined, bd = tol;
    for (const l of this.links) {
      if (!this.linkVisible(l)) continue;
      const [cx, cy] = control(l);
      const d = l.bend  // curva: dos tramos hasta el punto medio real de la cuadrática
        ? Math.min(distToSegment(wx, wy, l.source.x!, l.source.y!, (l.source.x! + 2 * cx + l.target.x!) / 4, (l.source.y! + 2 * cy + l.target.y!) / 4),
                   distToSegment(wx, wy, (l.source.x! + 2 * cx + l.target.x!) / 4, (l.source.y! + 2 * cy + l.target.y!) / 4, l.target.x!, l.target.y!))
        : distToSegment(wx, wy, l.source.x!, l.source.y!, l.target.x!, l.target.y!);
      if (d < bd) { bd = d; best = l; }
    }
    return best;
  }

  private onDown(ev: PointerEvent) {
    if (ev.button !== 0) return;
    if (this.inMini(ev.offsetX, ev.offsetY)) { this.miniJump(ev.offsetX, ev.offsetY); return; }
    this.down = { x: ev.offsetX, y: ev.offsetY };
    const n = this.nodeAt(ev.offsetX, ev.offsetY);
    if (!n) return;
    this.canvas.setPointerCapture(ev.pointerId);
    this.drag = { node: n, x0: ev.offsetX, y0: ev.offsetY, moved: false };
  }

  private onMove(ev: PointerEvent) {
    if (this.drag) {
      const d = this.drag;
      if (!d.moved && Math.hypot(ev.offsetX - d.x0, ev.offsetY - d.y0) < CLICK_SLOP) return;
      const sim = this.layout === "force" && !this.paused;
      if (!d.moved) { d.moved = true; if (sim) this.sim.alphaTarget(0.3).restart(); }
      [d.node.fx, d.node.fy] = this.toWorld(ev.offsetX, ev.offsetY);
      if (!sim) { d.node.x = d.node.fx; d.node.y = d.node.fy; }
      this.request();
      return;
    }
    if (this.inMini(ev.offsetX, ev.offsetY)) {
      if (this.hover) this.events.hover?.(null, 0, 0);
      this.hover = null; this.aim(null); this.canvas.style.cursor = "pointer"; this.request();
      return;
    }
    const n = this.nodeAt(ev.offsetX, ev.offsetY);
    const h = n?.id ?? (this.linkAt(ev.offsetX, ev.offsetY) ? "link" : null);
    if (h !== this.hover) {
      this.hover = h; this.canvas.style.cursor = h ? "pointer" : "";
      this.aim(n?.id ?? null);
      if (n) { const [sx, sy] = this.t.apply([n.x!, n.y!]); this.events.hover?.(n.id, sx, sy - n.size * this.t.k); } else this.events.hover?.(null, 0, 0);
      this.request();
    }
  }

  private onUp(ev: PointerEvent) {
    const d = this.drag, down = this.down;
    this.drag = null; this.down = null;
    if (d) {
      if (this.canvas.hasPointerCapture(ev.pointerId)) this.canvas.releasePointerCapture(ev.pointerId);
      if (d.moved) { this.release(d.node); return; }
      this.events.nodeClick?.(d.node.id);
      return;
    }
    if (ev.button !== 0 || !down || Math.hypot(ev.offsetX - down.x, ev.offsetY - down.y) >= CLICK_SLOP) return;  // fue un arrastre del lienzo
    const l = this.linkAt(ev.offsetX, ev.offsetY);
    if (l) this.events.linkClick?.(l.id); else this.events.backgroundClick?.();
  }

  private endDrag() {
    const d = this.drag;
    this.drag = null; this.down = null;
    if (d?.moved) this.release(d.node);
  }

  /** Fin de un arrastre: el nodo se queda donde se soltó, para apartarlo y ver lo que lo rodea. En fuerza queda fijado
   * (con una marca) hasta un doble clic o «Restablecer posiciones». */
  private release(n: SNode) {
    if (this.layout !== "force") return;
    n.pinned = true; this.sim.alphaTarget(0); this.request();
  }

  /** Suelta nodos fijados y deja que la simulación los recoloque. */
  private unpin(ns: SNode[]) {
    for (const n of ns) { n.fx = null; n.fy = null; n.pinned = false; }
    if (this.still || this.paused) this.settle(0.5); else this.sim.alpha(Math.max(this.sim.alpha(), 0.5)).restart();
    this.request();
  }

  resetPositions() {
    if (this.layout === "force") { this.unpin(this.nodes.filter((n) => n.pinned)); this.fit(this.still ? 0 : MORPH_MS + 200); }
    else { this.place(true); this.fit(this.still ? 0 : MORPH_MS + 200); }
  }

  /** El foco por señalar llega con retraso: pasar de largo por varios nodos no enciende ni apaga nada. */
  private aim(id: string | null) {
    clearTimeout(this.focusTimer);
    if (id === this.focusHover) return;
    this.focusTimer = window.setTimeout(() => { this.focusHover = id; this.request(); }, FOCUS_DELAY);
  }

  private inMini(x: number, y: number) { const m = this.mini; return !!m && x >= m.x && x <= m.x + MINI_W && y >= m.y && y <= m.y + MINI_H; }

  /** Clic en el minimapa: centra la vista en ese punto con el mismo zoom. */
  private miniJump(x: number, y: number) {
    const m = this.mini!, wx = (x - m.ox) / m.s, wy = (y - m.oy) / m.s, k = this.t.k;
    this.animateTo(() => zoomIdentity.translate(this.w / 2 - k * wx, this.h / 2 - k * wy).scale(k), 300);
  }

  private animateTo(goal: () => ZoomTransform, ms: number) {
    cancelAnimationFrame(this.anim);
    const sel = select(this.canvas);
    if (this.still) ms = 0;
    if (ms <= 0) { this.zoomer.transform(sel, goal()); return; }
    const from = this.t, start = performance.now();
    const step = (now: number) => {
      const p = ease(Math.min(1, (now - start) / ms)), target = goal();
      const k = from.k * Math.pow(target.k / from.k, p);
      this.zoomer.transform(sel, zoomIdentity.translate(from.x + (target.x - from.x) * p, from.y + (target.y - from.y) * p).scale(k));
      if (p < 1 || (this.moving() && now - start < FOLLOW_MS)) this.anim = requestAnimationFrame(step);  // sigue al nodo mientras la simulación lo mueva
    };
    this.anim = requestAnimationFrame(step);
  }

  // --- dibujo --------------------------------------------------------------------------------
  private linkVisible(l: SLink) { return l.visible && l.source.visible && l.target.visible && l.source.x !== undefined; }

  private request() {
    if (!this.frame) this.frame = requestAnimationFrame(() => { this.frame = 0; this.draw(); });
  }

  private draw() {
    const { ctx, t } = this;
    const now = performance.now();
    this.measure(now);
    const full = this.effective === "full";
    let animating = false;
    if (this.morph) {  // cambio de disposición: de donde estaba a su sitio nuevo
      const p = Math.min(1, (now - this.morph.start) / MORPH_MS), e = ease(p);
      for (const n of this.nodes) { const f = this.morph.from.get(n.id); if (f && n.fx != null) { n.x = f[0] + (n.fx - f[0]) * e; n.y = f[1] + (n.fy! - f[1]) * e; } }
      if (p >= 1) this.morph = null; else animating = true;
    }
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.fillStyle = CANVAS.background;
    ctx.fillRect(0, 0, this.w, this.h);
    ctx.setTransform(this.dpr * t.k, 0, 0, this.dpr * t.k, this.dpr * t.x, this.dpr * t.y);
    const [vx0, vy0] = this.toWorld(0, 0), [vx1, vy1] = this.toWorld(this.w, this.h);
    const onScreen = (x: number, y: number, m = 0) => x >= vx0 - m && x <= vx1 + m && y >= vy0 - m && y <= vy1 + m;
    const links = this.links.filter((l) => this.linkVisible(l));
    const px = 1 / t.k;  // un píxel de pantalla en unidades del mundo
    const cap = full ? MAX_LABELS : MAX_LABELS_REDUCED;

    // foco: el nodo señalado un momento (o el seleccionado) y su vecindario; lo demás se atenúa con un fundido, halos incluidos.
    // Con «Reducido» o con menos movimiento en el sistema, señalar no atenúa nada: solo el nodo seleccionado hace de foco.
    const calm = !full || this.still;
    const hoverNode = !calm && this.focusHover && this.byId.has(this.focusHover) ? this.focusHover : null;
    const focusId = [hoverNode, this.selectedNode].find((id) => id && this.byId.get(id)?.visible) ?? null;  // un nodo oculto por un filtro no hace de foco
    const near = new Set<string>();
    if (focusId) { near.add(focusId); for (const l of links) if (l.source.id === focusId || l.target.id === focusId) { near.add(l.source.id); near.add(l.target.id); } }
    const touches = (l: SLink) => !focusId || l.source.id === focusId || l.target.id === focusId;
    const dt = now - this.fadeAt > 100 ? 16 : now - this.fadeAt, step = dt / FADE_MS;  // tras un rato quieto, el primer paso es el de un fotograma
    this.fadeAt = now;
    const fade = (cur: number | undefined, to: number) => { const c = cur ?? 1; if (c === to) return c; animating = true; return c < to ? Math.min(to, c + step) : Math.max(to, c - step); };
    this.haloLit = fade(this.haloLit, focusId ? 0 : 1);
    for (const n of this.nodes) n.lit = fade(n.lit, !focusId || near.has(n.id) ? 1 : 0);
    for (const l of links) l.lit = fade(l.lit, touches(l) ? 1 : 0);
    if (this.layout === "force") this.drawHalos(px, 0.35 + 0.65 * this.haloLit);

    // aristas, agrupadas por estilo para trazar cada grupo de una vez
    const groups = new Map<string, SLink[]>();
    for (const l of links) {
      if (l.id === this.selectedLink) continue;
      const k = `${l.color}|${l.dashed ? 1 : 0}|${l.strong ? 1 : 0}|${Math.round((l.lit ?? 1) * 20) / 20}`;
      (groups.get(k) ?? groups.set(k, []).get(k)!).push(l);
    }
    const stroke = (ls: SLink[], color: string, dashed: boolean, width: number, alpha: number) => {
      ctx.beginPath();
      for (const l of ls) {
        ctx.moveTo(l.source.x!, l.source.y!);
        if (l.bend) { const [cx, cy] = control(l); ctx.quadraticCurveTo(cx, cy, l.target.x!, l.target.y!); } else ctx.lineTo(l.target.x!, l.target.y!);
      }
      ctx.setLineDash(dashed ? [4 * px, 4 * px] : []);
      ctx.strokeStyle = color; ctx.lineWidth = width * px; ctx.globalAlpha = 0.75 * alpha;
      ctx.stroke();
      ctx.globalAlpha = alpha;
      ctx.beginPath();  // puntas de flecha en el borde del nodo destino
      for (const l of ls) {
        const [cx, cy] = control(l);
        const ang = Math.atan2(l.target.y! - cy, l.target.x! - cx), r = l.target.size + 1.5 * px, a = 6 * px;
        const ex = l.target.x! - Math.cos(ang) * r, ey = l.target.y! - Math.sin(ang) * r;
        ctx.moveTo(ex, ey);
        ctx.lineTo(ex - Math.cos(ang - 0.4) * a, ey - Math.sin(ang - 0.4) * a);
        ctx.lineTo(ex - Math.cos(ang + 0.4) * a, ey - Math.sin(ang + 0.4) * a);
        ctx.closePath();
      }
      ctx.setLineDash([]);
      ctx.fillStyle = color; ctx.fill();
      ctx.globalAlpha = 1;
    };
    for (const [k, ls] of groups) { const [color, dashed, strong, lit] = k.split("|"); stroke(ls, color, dashed === "1", strong === "1" ? 2.6 : 1.2, DIM * 0.6 + (1 - DIM * 0.6) * Number(lit)); }
    const selLink = links.find((l) => l.id === this.selectedLink);
    if (selLink) stroke([selLink], CANVAS.selected, selLink.dashed, 2.5, 1);

    // partículas: solo en las aristas válidas del nodo señalado, y solo mientras se señala (en reposo no se anima nada).
    // Lentas, pequeñas y discretas, y entran con el mismo fundido que el foco.
    if (hoverNode) {
      const lit = links.filter((l) => !l.dashed && touches(l)).slice(0, 60);
      ctx.fillStyle = CANVAS.foreground; ctx.globalAlpha = 0.45 * (1 - this.haloLit);
      for (const l of lit) {
        const [cx, cy] = control(l), q = (now / PARTICLE_MS + hash(l.id)) % 1, r = 1 - q;
        ctx.beginPath();
        ctx.arc(r * r * l.source.x! + 2 * r * q * cx + q * q * l.target.x!, r * r * l.source.y! + 2 * r * q * cy + q * q * l.target.y!, 1.6 * px, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      animating ||= lit.length > 0;
    }

    // etiqueta del tipo de relación sobre cada arista, a lo largo de ella y siempre legible (nunca boca abajo).
    // Con foco, solo las suyas; si en pantalla hay más del tope, solo las de lo seleccionado o señalado.
    const mid = (l: SLink): [number, number] => { const [cx, cy] = control(l); return [(l.source.x! + 2 * cx + l.target.x!) / 4, (l.source.y! + 2 * cy + l.target.y!) / 4]; };
    let labelled = t.k >= LABEL_ZOOM ? links.filter((l) => l.label && (touches(l) || (l.lit ?? 1) > 0.02) && onScreen(...mid(l), 50)) : [];
    if (labelled.length > cap) labelled = labelled.filter((l) => l.id === this.selectedLink || (focusId && touches(l))).slice(0, cap);
    if (selLink && !labelled.includes(selLink)) labelled.push(selLink);
    if (labelled.length) {
      ctx.font = FONT; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const fs = 1 / Math.max(t.k, 1);  // con mucho zoom el texto no crece sin límite
      for (const l of labelled) {
        const [mx, my] = mid(l);
        let ang = Math.atan2(l.target.y! - l.source.y!, l.target.x! - l.source.x!);
        if (ang > Math.PI / 2 || ang < -Math.PI / 2) ang += Math.PI;
        ctx.save();
        ctx.globalAlpha = l.id === this.selectedLink ? 1 : l.lit ?? 1;
        ctx.translate(mx, my); ctx.rotate(ang); ctx.scale(fs, fs);
        const txt = l.label.length > 28 ? l.label.slice(0, 27) + "…" : l.label;
        ctx.lineWidth = 3; ctx.strokeStyle = CANVAS.background; ctx.strokeText(txt, 0, -6);
        ctx.fillStyle = l.id === this.selectedLink ? CANVAS.selected : CANVAS.label; ctx.fillText(txt, 0, -6);
        ctx.restore();
      }
    }

    // nodos: los nuevos entran apareciendo y creciendo; fuera del foco, atenuados
    const named: SNode[] = [];
    for (const n of this.nodes) {
      if (!n.visible || n.x === undefined || !onScreen(n.x, n.y!, n.size + 80)) continue;
      const b = this.born.get(n.id);
      let e = 1;
      if (b !== undefined) {
        e = Math.min(1, (now - b) / ENTER_MS);
        if (e >= 1) this.born.delete(n.id); else animating = true;
        e = 1 - Math.pow(1 - e, 3);
      }
      const lit = n.lit ?? 1, alpha = (DIM + (1 - DIM) * lit) * e;
      if (near.has(n.id) || lit > 0.02) named.push(n);
      if (!onScreen(n.x, n.y!, n.size)) continue;
      const r = n.size * (0.4 + 0.6 * e);
      ctx.globalAlpha = alpha;
      ctx.beginPath(); ctx.arc(n.x, n.y!, r, 0, Math.PI * 2);
      ctx.fillStyle = n.color; ctx.fill();
      const sel = n.id === this.selectedNode, hov = n.id === this.hover;
      if (n.ring && !sel) {  // respaldado por varios orígenes
        ctx.beginPath(); ctx.arc(n.x, n.y!, r + 3 * px, 0, Math.PI * 2);
        ctx.lineWidth = 1.5 * px; ctx.strokeStyle = CANVAS.foreground; ctx.stroke();
      }
      if (sel || hov) { ctx.lineWidth = (sel ? 3 : 2) * px; ctx.strokeStyle = sel ? CANVAS.selected : CANVAS.foreground; ctx.stroke(); }
      if (n.pinned) {  // fijado al arrastrarlo: un punto en el borde (doble clic lo suelta)
        const a = -Math.PI / 4, cx = n.x + Math.cos(a) * r, cy = n.y! + Math.sin(a) * r;
        ctx.globalAlpha = Math.max(alpha, 0.6);
        ctx.beginPath(); ctx.arc(cx, cy, 3 * px, 0, Math.PI * 2);
        ctx.fillStyle = CANVAS.foreground; ctx.fill(); ctx.lineWidth = 1.5 * px; ctx.strokeStyle = CANVAS.background; ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
    // nombres (con el mismo tope de textos por fotograma; con foco, solo los del vecindario: los demás se desvanecen con su nodo)
    const shown = named;
    const all = t.k >= CAPTION_ZOOM && (focusId ? named.filter((n) => near.has(n.id)).length : named.length) <= cap;
    if (all || focusId) {
      ctx.font = FONT; ctx.textAlign = "center"; ctx.textBaseline = "top";
      const fs = 1 / Math.max(t.k, 1);
      for (const n of shown) {
        const focus = n.id === this.selectedNode || n.id === this.hover;
        if (!all && !focus) continue;
        const txt = !focus && n.caption.length > 24 ? n.caption.slice(0, 23) + "…" : n.caption;
        ctx.save(); ctx.globalAlpha = focus ? 1 : n.lit ?? 1; ctx.translate(n.x!, n.y! + n.size + 2 * px); ctx.scale(fs, fs);
        ctx.lineWidth = 3; ctx.strokeStyle = CANVAS.background; ctx.strokeText(txt, 0, 0);
        ctx.fillStyle = CANVAS.foreground; ctx.fillText(txt, 0, 0);
        ctx.restore();
      }
    }
    this.drawMinimap(full);
    if (animating) this.request();
  }

  /** Modo automático: si los fotogramas seguidos van lentos de forma sostenida, baja a reducido (una vez por lienzo).
   * Solo cuenta fotogramas consecutivos, es decir, mientras algo se anima: en reposo no se dibuja nada. */
  private measure(now: number) {
    const dt = now - this.lastDraw;
    this.lastDraw = now;
    if (this.mode !== "auto" || this.effective !== "full" || dt > 250) return;
    this.slow = dt > SLOW_MS ? this.slow + 1 : Math.max(0, this.slow - 2);
    if (this.slow >= SLOW_FRAMES) { this.autoDown = true; this.applyEffects(); }
  }

  /** Minimapa en la esquina con todos los nodos visibles y el rectángulo de la vista; un clic centra ahí. */
  private drawMinimap(full: boolean) {
    const vis = this.nodes.filter((n) => n.visible && n.x !== undefined);
    if (!full || vis.length < MINIMAP_MIN || this.w < MINI_W * 2.5 || this.h < MINI_H * 2.5) { this.mini = null; return; }
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of vis) { x0 = Math.min(x0, n.x!); y0 = Math.min(y0, n.y!); x1 = Math.max(x1, n.x!); y1 = Math.max(y1, n.y!); }
    const x = this.w - MINI_W - 10, y = this.h - MINI_H - 10, s = Math.min((MINI_W - 12) / Math.max(x1 - x0, 1), (MINI_H - 12) / Math.max(y1 - y0, 1));
    const ox = x + (MINI_W - (x1 - x0) * s) / 2 - x0 * s, oy = y + (MINI_H - (y1 - y0) * s) / 2 - y0 * s;
    const { ctx } = this;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.globalAlpha = 0.88; ctx.fillStyle = CANVAS.background; ctx.fillRect(x, y, MINI_W, MINI_H);
    ctx.globalAlpha = 1; ctx.strokeStyle = CANVAS.label; ctx.lineWidth = 1; ctx.strokeRect(x + 0.5, y + 0.5, MINI_W - 1, MINI_H - 1);
    for (const n of vis) { ctx.fillStyle = n.color; ctx.fillRect(ox + n.x! * s - 1, oy + n.y! * s - 1, 2, 2); }
    const [vx0, vy0] = this.toWorld(0, 0), [vx1, vy1] = this.toWorld(this.w, this.h);
    const rx0 = Math.max(x, ox + vx0 * s), ry0 = Math.max(y, oy + vy0 * s), rx1 = Math.min(x + MINI_W, ox + vx1 * s), ry1 = Math.min(y + MINI_H, oy + vy1 * s);
    if (rx1 > rx0 && ry1 > ry0) { ctx.strokeStyle = CANVAS.selected; ctx.strokeRect(rx0, ry0, rx1 - rx0, ry1 - ry0); }
    this.mini = { x, y, ox, oy, s };
  }

  /** Zona translúcida del color de cada origen alrededor de sus nodos visibles (envolvente convexa suavizada), con su nombre y recuento. */
  private drawHalos(px: number, fade: number) {
    const { ctx } = this;
    const placed: [number, number, number][] = [];  // rótulos ya puestos (centro y ancho en pantalla): dos halos con la misma cima no se pisan
    for (const h of this.halos) {
      const ns = this.nodes.filter((n) => n.visible && n.x !== undefined && n.groups?.includes(h.key));
      if (ns.length < 2) continue;
      const pts: [number, number][] = [];
      for (const n of ns) for (let i = 0; i < 8; i++) { const a = (i * Math.PI) / 4, r = n.size + HALO_PAD; pts.push([n.x! + Math.cos(a) * r, n.y! + Math.sin(a) * r]); }
      const hull = polygonHull(pts);
      if (!hull) continue;
      const mid = (a: [number, number], b: [number, number]): [number, number] => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      ctx.beginPath();
      let m = mid(hull[hull.length - 1], hull[0]);
      ctx.moveTo(m[0], m[1]);
      hull.forEach((q, i) => { m = mid(q, hull[(i + 1) % hull.length]); ctx.quadraticCurveTo(q[0], q[1], m[0], m[1]); });
      ctx.closePath();
      ctx.fillStyle = h.color; ctx.globalAlpha = 0.08 * fade; ctx.fill();
      ctx.strokeStyle = h.color; ctx.globalAlpha = 0.4 * fade; ctx.lineWidth = 1.2 * px; ctx.setLineDash([]); ctx.stroke();
      ctx.globalAlpha = fade;
      const top = hull.reduce((a, b) => (b[1] < a[1] ? b : a));  // nombre sobre la corona del halo, a tamaño de pantalla constante
      const label = `${h.name.length > 22 ? h.name.slice(0, 21) + "…" : h.name} · ${ns.length}`;
      ctx.font = FONT;
      const lw = ctx.measureText(label).width, [sx, sy0] = this.t.apply(top);
      let sy = sy0 - 4;
      while (placed.some(([x, y, w]) => Math.abs(x - sx) < (w + lw) / 2 + 4 && Math.abs(y - sy) < 14)) sy -= 14;
      placed.push([sx, sy, lw]);
      ctx.save(); ctx.translate(top[0], top[1] + (sy - sy0) * px); ctx.scale(px, px);
      ctx.textAlign = "center"; ctx.textBaseline = "bottom";
      ctx.lineWidth = 3; ctx.strokeStyle = CANVAS.background; ctx.strokeText(label, 0, 0);
      ctx.fillStyle = h.color; ctx.fillText(label, 0, 0);
      ctx.restore();
      ctx.globalAlpha = 1;
    }
  }
}
