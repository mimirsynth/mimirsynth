import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type Simulation, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";
import { polygonHull } from "d3-polygon";
import { quadtree } from "d3-quadtree";
import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from "d3-zoom";
import { CANVAS } from "../palette";

/** Lo que el renderer necesita de cada nodo y arista; el resto de la pantalla no ve d3 ni el canvas. */
/** `groups`: claves de los halos (orígenes) a los que pertenece el nodo; `ring`: respaldado por 2 o más orígenes. */
export type RNode = { id: string; color: string; size: number; caption: string; visible: boolean; groups?: string[]; ring?: boolean };
/** `strong`: hecho respaldado por 2 o más orígenes (se dibuja más grueso). */
export type RLink = { id: string; source: string; target: string; label: string; color: string; dashed: boolean; visible: boolean; strong?: boolean };
/** Halo de un origen: envuelve a sus nodos y los atrae hacia su ancla. El orden es el de la leyenda. */
export type RHalo = { key: string; name: string; color: string };
export type RendererEvents = {
  nodeClick?: (id: string) => void;
  nodeContextMenu?: (id: string) => void;
  linkClick?: (id: string) => void;
  backgroundClick?: () => void;
};

type SNode = RNode & SimulationNodeDatum & { ax?: number; ay?: number; pull?: number };  // ancla: media de las de sus halos
type SLink = Omit<RLink, "source" | "target"> & SimulationLinkDatum<SNode> & { source: SNode; target: SNode; bend: number };

const FONT = "11px system-ui, -apple-system, 'Segoe UI', sans-serif";
const SETTLE_MS = 400;           // presupuesto para pre-asentar un grafo nuevo antes de pintarlo
const LABEL_ZOOM = 0.7;          // por debajo, las etiquetas de las aristas no se leen y solo ensucian
const CAPTION_ZOOM = 0.45;
const CLICK_SLOP = 4;            // píxeles que puede moverse el puntero y seguir siendo un clic
const HALO_PAD = 26;             // margen del halo alrededor de cada nodo
const PULL = 0.15;               // fuerza hacia el ancla de los orígenes: alta para que un origen con pocos enlaces no se disperse
const PULL_NONE = 0.04;
const LINK = 0.3;
const LINK_WITH_HALOS = 0.08;
const CHARGE = -220;
const CHARGE_WITH_HALOS = -90;  // con halos, la repulsión no debe deshacer los grupos

/** Hash estable de un id → [0, 1): la posición inicial no depende del orden en que llegan los datos. */
function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return ((h >>> 0) % 100000) / 100000;
}

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
export class ForceRenderer {
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
  private drag: { node: SNode; x0: number; y0: number; moved: boolean } | null = null;
  private down: { x: number; y: number } | null = null;
  private anim = 0;
  private pendingFit: (() => void) | null = null;  // encuadre pedido antes de conocer el tamaño del lienzo
  private cleanup: (() => void)[] = [];
  private halos: RHalo[] = [];
  private anchorSig = "";

  constructor(private canvas: HTMLCanvasElement, private events: RendererEvents = {}) {
    this.ctx = canvas.getContext("2d")!;
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
      .filter((ev: any) => (ev.type === "wheel" || !this.nodeAt(ev.offsetX, ev.offsetY)) && !ev.button)
      .on("zoom", (ev) => { if (ev.sourceEvent) cancelAnimationFrame(this.anim); this.t = ev.transform; this.request(); });  // el usuario manda sobre un encuadre en curso
    select(canvas).call(this.zoomer).on("dblclick.zoom", null);
    const on = <K extends keyof HTMLElementEventMap>(type: K, fn: (ev: HTMLElementEventMap[K]) => void) => {
      canvas.addEventListener(type, fn as EventListener);
      this.cleanup.push(() => canvas.removeEventListener(type, fn as EventListener));
    };
    on("pointerdown", (ev) => this.onDown(ev));
    on("pointermove", (ev) => this.onMove(ev));
    on("pointerup", (ev) => this.onUp(ev));
    on("pointerleave", () => { if (this.hover) { this.hover = null; this.canvas.style.cursor = ""; this.request(); } });
    on("contextmenu", (ev) => {
      const n = this.nodeAt(ev.offsetX, ev.offsetY);
      if (n) { ev.preventDefault(); this.events.nodeContextMenu?.(n.id); }
    });
  }

  setEvents(events: RendererEvents) { this.events = events; }

  resize(w: number, h: number) {
    this.dpr = window.devicePixelRatio || 1;
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
    if (sameTopo) {
      if (reanchor && !this.paused) this.sim.alpha(Math.max(this.sim.alpha(), 0.5)).restart();  // otros halos: los nodos se recolocan animados
      this.request();
      return;
    }
    const fresh = this.nodes.filter((n) => n.x === undefined);
    for (const n of fresh) {
      const nb = this.links.find((l) => (l.source === n && l.target.x !== undefined) || (l.target === n && l.source.x !== undefined));
      const anchor = nb ? (nb.source === n ? nb.target : nb.source) : null;
      if (anchor) { n.x = anchor.x! + (hash(n.id) - 0.5) * 60; n.y = anchor.y! + (hash(n.id + "y") - 0.5) * 60; } else seed(n);
    }
    this.sim.nodes(this.nodes);
    (this.sim.force("link") as any).links(this.links);
    if (!kept) {
      this.sim.alpha(1);
      const end = performance.now() + SETTLE_MS;
      while (this.sim.alpha() > this.sim.alphaMin() && performance.now() < end) this.sim.tick();
      this.fit(0);
    }
    this.sim.alpha(kept ? 0.4 : this.sim.alpha());
    if (!this.paused) this.sim.restart();
    this.request();
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
      const shared = new Map<string, number>();
      for (const n of this.nodes) {
        const g = (n.groups ?? []).filter((k) => keys.includes(k));
        for (let i = 0; i < g.length; i++) for (let j = i + 1; j < g.length; j++) for (const k of [`${g[i]}|${g[j]}`, `${g[j]}|${g[i]}`]) shared.set(k, (shared.get(k) ?? 0) + 1);
      }
      const order = [keys[0]], left = keys.slice(1);
      while (left.length) {  // cadena voraz: a continuación, el que más comparte con el último colocado
        const last = order[order.length - 1];
        let bi = 0;
        left.forEach((k, i) => { if ((shared.get(`${last}|${k}`) ?? 0) > (shared.get(`${last}|${left[bi]}`) ?? 0)) bi = i; });
        order.push(left.splice(bi, 1)[0]);
      }
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

  setSelection(node: string | null, link: string | null) {
    if (node === this.selectedNode && link === this.selectedLink) return;
    this.selectedNode = node; this.selectedLink = link; this.request();
  }

  setPaused(p: boolean) {
    this.paused = p;
    if (p) this.sim.stop(); else this.sim.alpha(Math.max(this.sim.alpha(), 0.1)).restart();
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
      if (!d.moved) { d.moved = true; if (!this.paused) this.sim.alphaTarget(0.3).restart(); }
      [d.node.fx, d.node.fy] = this.toWorld(ev.offsetX, ev.offsetY);
      if (this.paused) { d.node.x = d.node.fx; d.node.y = d.node.fy; }
      this.request();
      return;
    }
    const n = this.nodeAt(ev.offsetX, ev.offsetY);
    const h = n?.id ?? (this.linkAt(ev.offsetX, ev.offsetY) ? "link" : null);
    if (h !== this.hover) { this.hover = h; this.canvas.style.cursor = h ? "pointer" : ""; this.request(); }
  }

  private onUp(ev: PointerEvent) {
    const d = this.drag, down = this.down;
    this.drag = null; this.down = null;
    if (d) {
      this.canvas.releasePointerCapture(ev.pointerId);
      if (d.moved) { d.node.fx = null; d.node.fy = null; this.sim.alphaTarget(0); return; }
      this.events.nodeClick?.(d.node.id);
      return;
    }
    if (ev.button !== 0 || !down || Math.hypot(ev.offsetX - down.x, ev.offsetY - down.y) >= CLICK_SLOP) return;  // fue un arrastre del lienzo
    const l = this.linkAt(ev.offsetX, ev.offsetY);
    if (l) this.events.linkClick?.(l.id); else this.events.backgroundClick?.();
  }

  private animateTo(goal: () => ZoomTransform, ms: number) {
    cancelAnimationFrame(this.anim);
    const sel = select(this.canvas);
    if (ms <= 0) { this.zoomer.transform(sel, goal()); return; }
    const from = this.t, start = performance.now();
    const ease = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
    const step = (now: number) => {
      const p = ease(Math.min(1, (now - start) / ms)), target = goal();
      const k = from.k * Math.pow(target.k / from.k, p);
      this.zoomer.transform(sel, zoomIdentity.translate(from.x + (target.x - from.x) * p, from.y + (target.y - from.y) * p).scale(k));
      if (p < 1 || (!this.paused && this.sim.alpha() > 0.03)) this.anim = requestAnimationFrame(step);  // sigue al nodo mientras la simulación lo mueva
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
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.fillStyle = CANVAS.background;
    ctx.fillRect(0, 0, this.w, this.h);
    ctx.setTransform(this.dpr * t.k, 0, 0, this.dpr * t.k, this.dpr * t.x, this.dpr * t.y);
    const [vx0, vy0] = this.toWorld(0, 0), [vx1, vy1] = this.toWorld(this.w, this.h);
    const onScreen = (x: number, y: number, m = 0) => x >= vx0 - m && x <= vx1 + m && y >= vy0 - m && y <= vy1 + m;
    const links = this.links.filter((l) => this.linkVisible(l));
    const px = 1 / t.k;  // un píxel de pantalla en unidades del mundo
    this.drawHalos(px);

    // aristas, agrupadas por estilo para trazar cada grupo de una vez
    const groups = new Map<string, SLink[]>();
    for (const l of links) {
      if (l.id === this.selectedLink) continue;
      const k = `${l.color}|${l.dashed ? 1 : 0}|${l.strong ? 1 : 0}`;
      (groups.get(k) ?? groups.set(k, []).get(k)!).push(l);
    }
    const stroke = (ls: SLink[], color: string, dashed: boolean, width: number) => {
      ctx.beginPath();
      for (const l of ls) {
        ctx.moveTo(l.source.x!, l.source.y!);
        if (l.bend) { const [cx, cy] = control(l); ctx.quadraticCurveTo(cx, cy, l.target.x!, l.target.y!); } else ctx.lineTo(l.target.x!, l.target.y!);
      }
      ctx.setLineDash(dashed ? [4 * px, 4 * px] : []);
      ctx.strokeStyle = color; ctx.lineWidth = width * px; ctx.globalAlpha = 0.75;
      ctx.stroke();
      ctx.globalAlpha = 1;
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
    };
    for (const [k, ls] of groups) { const [color, dashed, strong] = k.split("|"); stroke(ls, color, dashed === "1", strong === "1" ? 2.6 : 1.2); }
    const selLink = links.find((l) => l.id === this.selectedLink);
    if (selLink) stroke([selLink], CANVAS.selected, selLink.dashed, 2.5);

    // etiqueta del tipo de relación sobre cada arista, a lo largo de ella y siempre legible (nunca boca abajo)
    if (t.k >= LABEL_ZOOM || selLink) {
      ctx.font = FONT; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const fs = 1 / Math.max(t.k, 1);  // con mucho zoom el texto no crece sin límite
      for (const l of t.k >= LABEL_ZOOM ? links : [selLink!]) {
        const [cx, cy] = control(l);
        const mx = (l.source.x! + 2 * cx + l.target.x!) / 4, my = (l.source.y! + 2 * cy + l.target.y!) / 4;
        if (!onScreen(mx, my, 50) || !l.label) continue;
        let ang = Math.atan2(l.target.y! - l.source.y!, l.target.x! - l.source.x!);
        if (ang > Math.PI / 2 || ang < -Math.PI / 2) ang += Math.PI;
        ctx.save();
        ctx.translate(mx, my); ctx.rotate(ang); ctx.scale(fs, fs);
        const txt = l.label.length > 28 ? l.label.slice(0, 27) + "…" : l.label;
        ctx.lineWidth = 3; ctx.strokeStyle = CANVAS.background; ctx.strokeText(txt, 0, -6);
        ctx.fillStyle = l.id === this.selectedLink ? CANVAS.selected : CANVAS.label; ctx.fillText(txt, 0, -6);
        ctx.restore();
      }
    }

    // nodos
    for (const n of this.nodes) {
      if (!n.visible || n.x === undefined || !onScreen(n.x, n.y!, n.size)) continue;
      ctx.beginPath(); ctx.arc(n.x, n.y!, n.size, 0, Math.PI * 2);
      ctx.fillStyle = n.color; ctx.fill();
      const sel = n.id === this.selectedNode, hov = n.id === this.hover;
      if (n.ring && !sel) {  // respaldado por varios orígenes
        ctx.beginPath(); ctx.arc(n.x, n.y!, n.size + 3 * px, 0, Math.PI * 2);
        ctx.lineWidth = 1.5 * px; ctx.strokeStyle = CANVAS.foreground; ctx.stroke();
      }
      if (sel || hov) { ctx.lineWidth = (sel ? 3 : 2) * px; ctx.strokeStyle = sel ? CANVAS.selected : CANVAS.foreground; ctx.stroke(); }
    }
    // nombres
    if (t.k >= CAPTION_ZOOM || this.selectedNode || this.hover) {
      ctx.font = FONT; ctx.textAlign = "center"; ctx.textBaseline = "top";
      const fs = 1 / Math.max(t.k, 1);
      for (const n of this.nodes) {
        const focus = n.id === this.selectedNode || n.id === this.hover;
        if (!n.visible || n.x === undefined || !onScreen(n.x, n.y!, 80) || (t.k < CAPTION_ZOOM && !focus)) continue;
        const txt = !focus && n.caption.length > 24 ? n.caption.slice(0, 23) + "…" : n.caption;
        ctx.save(); ctx.translate(n.x, n.y! + n.size + 2 * px); ctx.scale(fs, fs);
        ctx.lineWidth = 3; ctx.strokeStyle = CANVAS.background; ctx.strokeText(txt, 0, 0);
        ctx.fillStyle = CANVAS.foreground; ctx.fillText(txt, 0, 0);
        ctx.restore();
      }
    }
  }

  /** Zona translúcida del color de cada origen alrededor de sus nodos visibles (envolvente convexa suavizada), con su nombre y recuento. */
  private drawHalos(px: number) {
    const { ctx } = this;
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
      ctx.fillStyle = h.color; ctx.globalAlpha = 0.08; ctx.fill();
      ctx.strokeStyle = h.color; ctx.globalAlpha = 0.4; ctx.lineWidth = 1.2 * px; ctx.setLineDash([]); ctx.stroke();
      ctx.globalAlpha = 1;
      const top = hull.reduce((a, b) => (b[1] < a[1] ? b : a));  // nombre sobre la corona del halo, a tamaño de pantalla constante
      const label = `${h.name.length > 22 ? h.name.slice(0, 21) + "…" : h.name} · ${ns.length}`;
      ctx.save(); ctx.translate(top[0], top[1] - 4 * px); ctx.scale(px, px);
      ctx.font = FONT; ctx.textAlign = "center"; ctx.textBaseline = "bottom";
      ctx.lineWidth = 3; ctx.strokeStyle = CANVAS.background; ctx.strokeText(label, 0, 0);
      ctx.fillStyle = h.color; ctx.fillText(label, 0, 0);
      ctx.restore();
    }
  }
}
