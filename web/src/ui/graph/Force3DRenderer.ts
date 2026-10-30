import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { ConvexGeometry } from "three/examples/jsm/geometries/ConvexGeometry.js";
import { mergeVertices } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, forceZ } from "d3-force-3d";
import type { Simulation, SimulationNodeDatum } from "d3-force";
import { CANVAS } from "../palette";
import { anchorOrder, hash, placeLayout, type Layout } from "./layouts";
import { CHARGE, CHARGE_WITH_HALOS, DIM, ease, ENTER_MS, FADE_MS, FOCUS_DELAY, FOLLOW_MS, LINK, LINK_WITH_HALOS, MAX_LABELS, MAX_LABELS_REDUCED, MORPH_MS, PARTICLE_MS, PULL, PULL_NONE, SLOW_FRAMES, SLOW_MS,
  type Effects, type EffectsMode, type GraphRenderer, type RendererEvents, type RHalo, type RLink, type RNode } from "./types";

// `lit`: 1 a plena luz, 0 atenuado por el foco (con fundido); `pinned`: fijado al arrastrarlo
type SNode = RNode & SimulationNodeDatum & { z?: number; vz?: number; fz?: number | null; ax?: number; ay?: number; az?: number; pull?: number; lit?: number; pinned?: boolean };
type SLink = Omit<RLink, "source" | "target"> & { source: SNode; target: SNode; bend: number; lit?: number };

const FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif";
const FONT_PX = 28;              // tamaño del texto en su textura (se dibuja grande para que se lea nítido)
const TEXT_PX = 12;              // alto del texto en pantalla cuando el nodo está cerca…
const MIN_TEXT_PX = 7;           // …y por debajo de esto, lejos, no se pinta
const CAPTION_PX = 1;            // píxeles por unidad a partir de los que un nodo lleva nombre (en 2D, el zoom mínimo para los nombres)
const SETTLE_MS = 400;
const ALPHA_MIN = 0.02;          // la simulación para antes que la de d3 (0,001): por debajo los nodos apenas se mueven, y en 3D cada fotograma cuesta
const TICK_MS = 1000 / 60;       // avanza a 60 pasos por segundo aunque los fotogramas vayan más lentos, para asentarse en el mismo tiempo
const CLICK_SLOP = 4;
const HALO_PAD = 22;             // margen del volumen del halo alrededor de cada nodo
const HALO_EVERY = 120;          // mientras algo se mueve, la envolvente se recalcula como mucho cada tantos ms
const HALO_ALPHA = 0.3;          // opacidad del borde del volumen; el interior queda casi transparente
const MANY_LINKS = 150;          // con más aristas visibles, las que no están en foco se aclaran para que el 3D se pueda leer
const LEVEL_DEPTH = 70;          // radial y árbol: cada nivel, un paso hacia el fondo
const CURVE = 8;                 // tramos de una arista curva
const TEXT_CACHE = 600;
/** Vértices de un icosaedro: puntos alrededor de cada nodo con los que se calcula la envolvente de su halo. */
const ICO = (() => { const g = new THREE.IcosahedronGeometry(1, 0), p = g.getAttribute("position"), out: THREE.Vector3[] = [], seen = new Set<string>();
  for (let i = 0; i < p.count; i++) { const v = new THREE.Vector3().fromBufferAttribute(p, i), k = v.toArray().map((x) => x.toFixed(3)).join(); if (!seen.has(k)) { seen.add(k); out.push(v); } }
  g.dispose(); return out; })();

/** Translúcido en el centro y más opaco en el contorno: así un volumen se lee como volumen y no tapa lo que hay dentro. */
const HALO_VERTEX = `varying vec3 vN; varying vec3 vV;
void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`;
const HALO_FRAGMENT = `uniform vec3 color; uniform float opacity; varying vec3 vN; varying vec3 vV;
void main() { float rim = 1.0 - abs(dot(normalize(vN), normalize(vV))); gl_FragColor = vec4(color, opacity * (0.08 + 0.92 * pow(rim, 2.5)));
#include <colorspace_fragment>
}`;

function seed(n: SNode) {
  const a = hash(n.id) * Math.PI * 2, b = Math.acos(2 * hash(n.id + "b") - 1), r = 40 + hash(n.id + "r") * 260;
  n.x = Math.sin(b) * Math.cos(a) * r; n.y = Math.cos(b) * r; n.z = Math.sin(b) * Math.sin(a) * r;
}

const pos = (n: SNode) => new THREE.Vector3(n.x ?? 0, n.y ?? 0, n.z ?? 0);

/** Grafo en 3D con WebGL: d3-force-3d para colocar, three.js para dibujar y OrbitControls para girar, mover y ampliar.
 * Misma interfaz y mismas reglas que el lienzo 2D: halos por origen (aquí, volúmenes), foco, entrada animada, partículas
 * y tope de textos; solo se dibuja cuando algo cambia. */
export class Force3DRenderer implements GraphRenderer {
  private gl: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(50, 1, 1, 50000);
  private controls: OrbitControls;
  private ray = new THREE.Raycaster();
  private nodes: SNode[] = [];
  private links: SLink[] = [];
  private byId = new Map<string, SNode>();
  private sim: Simulation<SNode, any>;
  private w = 0;
  private h = 0;
  private frame = 0;
  private anim = 0;
  private paused = false;
  private layout: Layout = "force";
  private root: string | undefined;
  private selectedNode: string | null = null;
  private selectedLink: string | null = null;
  private hover: string | null = null;
  private focusHover: string | null = null;  // nodo señalado que ya hace de foco: el ratón se quedó FOCUS_DELAY sobre él
  private focusTimer = 0;
  private fadeAt = 0;
  private haloLit = 1;
  private pins: THREE.Sprite[] = [];
  private halos: RHalo[] = [];
  private anchorSig = "";
  private mode: EffectsMode = "auto";
  private effective: Effects = "full";
  private autoDown = false;
  private slowSaid = false;
  private still: boolean;
  private born = new Map<string, number>();
  private morph: { from: Map<string, [number, number, number]>; start: number } | null = null;
  private lastDraw = 0;
  private lastTick = 0;
  private slow = 0;
  private pendingFit: (() => void) | null = null;
  private down: { x: number; y: number } | null = null;
  private drag: { node: SNode; plane: THREE.Plane; moved: boolean; x0: number; y0: number } | null = null;
  private cleanup: (() => void)[] = [];
  private colors = new Map<string, THREE.Color>();
  private bg = new THREE.Color(CANVAS.background);
  // objetos de la escena
  private sphere = new THREE.SphereGeometry(1, 16, 12);
  private sphereLow = new THREE.SphereGeometry(1, 8, 6);  // reducido: sin GPU, los polígonos de las esferas son lo que más cuesta
  private nodeMat = new THREE.MeshLambertMaterial();
  private nodeMesh: THREE.InstancedMesh;
  private drawn: SNode[] = [];   // nodo de cada instancia
  private lines: THREE.LineSegments;
  private dashes: THREE.LineSegments;
  private lineOwner: SLink[] = [];   // arista de cada tramo, para saber cuál se pulsa
  private dashOwner: SLink[] = [];
  private cone = new THREE.ConeGeometry(1, 1, 8).translate(0, -0.5, 0);  // punta en el origen, apuntando a +y
  private arrows: THREE.InstancedMesh;
  private particles: THREE.Points;
  private ringTex: THREE.CanvasTexture;
  private rings: THREE.Sprite[] = [];
  private pinTex: THREE.CanvasTexture;
  private labels: THREE.Sprite[] = [];
  private text = new Map<string, { tex: THREE.CanvasTexture; aspect: number }>();
  private haloObjs = new Map<string, { mesh: THREE.Mesh; mat: THREE.ShaderMaterial }>();
  private hullAt = 0;
  private hullDirty = true;

  constructor(private canvas: HTMLCanvasElement, private events: RendererEvents = {}) {
    this.gl = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.gl.setClearColor(this.bg, 1);
    this.still = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.scene.add(new THREE.AmbientLight(CANVAS.foreground, 1.6));
    const sun = new THREE.DirectionalLight(CANVAS.foreground, 1.4);
    sun.position.set(0.4, 1, 1);
    this.camera.add(sun);  // la luz va con la cámara: los nodos se ven igual desde cualquier lado
    this.scene.add(this.camera);
    this.camera.position.set(0, 120, 900);

    this.nodeMesh = new THREE.InstancedMesh(this.sphere, this.nodeMat, 1);
    this.nodeMesh.frustumCulled = false;
    this.scene.add(this.nodeMesh);
    const lineGeo = () => { const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(3), 3)); g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(3), 3)); return g; };
    this.lines = new THREE.LineSegments(lineGeo(), new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.85 }));
    this.dashes = new THREE.LineSegments(lineGeo(), new THREE.LineDashedMaterial({ vertexColors: true, transparent: true, opacity: 0.85, dashSize: 4, gapSize: 4 }));
    this.dashes.geometry.setAttribute("lineDistance", new THREE.BufferAttribute(new Float32Array(1), 1));
    for (const o of [this.lines, this.dashes]) { o.frustumCulled = false; this.scene.add(o); }
    this.arrows = new THREE.InstancedMesh(this.cone, new THREE.MeshBasicMaterial(), 1);
    this.arrows.frustumCulled = false;
    this.scene.add(this.arrows);
    const pg = new THREE.BufferGeometry();
    pg.setAttribute("position", new THREE.BufferAttribute(new Float32Array(3 * 120), 3));
    this.particles = new THREE.Points(pg, new THREE.PointsMaterial({ color: CANVAS.foreground, size: 3, sizeAttenuation: true, transparent: true, depthWrite: false }));
    this.particles.frustumCulled = false;
    this.scene.add(this.particles);
    this.ringTex = (() => {
      const c = document.createElement("canvas"); c.width = c.height = 64;
      const x = c.getContext("2d")!; x.strokeStyle = CANVAS.foreground; x.lineWidth = 5; x.beginPath(); x.arc(32, 32, 27, 0, Math.PI * 2); x.stroke();
      const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
    })();
    this.pinTex = (() => {
      const c = document.createElement("canvas"); c.width = c.height = 32;
      const x = c.getContext("2d")!; x.beginPath(); x.arc(16, 16, 12, 0, Math.PI * 2); x.fillStyle = CANVAS.foreground; x.fill(); x.lineWidth = 4; x.strokeStyle = CANVAS.background; x.stroke();
      const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
    })();

    this.sim = forceSimulation<SNode, any>([], 3)
      .force("link", forceLink<SNode, any>().id((d) => d.id).distance(70).strength(LINK))
      .force("charge", forceManyBody<SNode>().strength(CHARGE).distanceMax(600))
      .force("collide", forceCollide<SNode>((d) => d.size + 4))
      .force("x", forceX<SNode>((d) => d.ax ?? 0).strength((d) => d.pull ?? PULL_NONE))
      .force("y", forceY<SNode>((d) => d.ay ?? 0).strength((d) => d.pull ?? PULL_NONE))
      .force("z", forceZ<SNode>((d) => d.az ?? 0).strength((d) => d.pull ?? PULL_NONE) as any)
      .alphaMin(ALPHA_MIN)
      .on("tick", () => this.onTick())
      .stop();

    const on = <K extends keyof HTMLElementEventMap>(type: K, fn: (ev: HTMLElementEventMap[K]) => void) => {
      canvas.addEventListener(type, fn as EventListener);
      this.cleanup.push(() => canvas.removeEventListener(type, fn as EventListener));
    };
    // antes que los controles: un arrastre que empieza en un nodo mueve el nodo, no la cámara
    on("pointerdown", (ev) => this.onDown(ev));
    on("pointermove", (ev) => this.onMove(ev));
    on("pointerup", (ev) => this.onUp(ev));
    on("pointerleave", () => this.setHover(null));
    on("dblclick", (ev) => { const n = this.nodeAt(ev.offsetX, ev.offsetY); if (n?.pinned) this.unpin([n]); });
    on("pointercancel", () => this.endDrag());
    on("lostpointercapture", () => this.endDrag());
    on("contextmenu", (ev) => { const n = this.nodeAt(ev.offsetX, ev.offsetY); if (n) { ev.preventDefault(); this.events.nodeContextMenu?.(n.id); } });
    const lost = (ev: Event) => ev.preventDefault();
    canvas.addEventListener("webglcontextlost", lost);
    this.cleanup.push(() => canvas.removeEventListener("webglcontextlost", lost));
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = false;  // la inercia dibujaría fotogramas sin que nadie toque nada
    this.controls.addEventListener("change", () => this.request());
    this.controls.addEventListener("start", () => cancelAnimationFrame(this.anim));  // el usuario manda sobre un encuadre en curso
  }

  setEvents(events: RendererEvents) { this.events = events; }

  /** Un paso de la simulación por fotograma: si los fotogramas van lentos (sin GPU, muchos halos), se recuperan los pasos perdidos
   * para que el grafo se asiente en el mismo tiempo y deje de pintar. */
  private onTick() {
    const now = performance.now(), dt = now - this.lastTick;
    this.lastTick = now;
    const extra = dt < 250 ? Math.min(3, Math.round(dt / TICK_MS) - 1) : 0;
    if (extra > 0) this.sim.tick(extra);
    this.hullDirty = true;
    this.request();
  }

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
    if (w === this.w && h === this.h) return;
    const first = !this.w;
    this.w = w; this.h = h;
    this.gl.setPixelRatio(window.devicePixelRatio || 1);
    this.gl.setSize(w, h, false);
    this.canvas.style.width = `${w}px`; this.canvas.style.height = `${h}px`;
    this.camera.aspect = w / Math.max(h, 1);
    this.camera.updateProjectionMatrix();
    if (first) { const f = this.pendingFit ?? (() => this.fit(0)); this.pendingFit = null; if (this.nodes.length) f(); }
    this.request();
  }

  setData(nodes: RNode[], links: RLink[], halos: RHalo[] = []) {
    const old = this.byId;
    this.halos = halos;
    const kept = nodes.filter((n) => old.has(n.id)).length;
    const sameTopo = kept === nodes.length && kept === old.size && links.length === this.links.length && links.every((l, i) => this.links[i]?.id === l.id);
    this.byId = new Map();
    this.nodes = nodes.map((n) => { const s = Object.assign(old.get(n.id) ?? ({} as SNode), n); this.byId.set(n.id, s); return s; });
    const pairs = new Map<string, number>();
    this.links = links.filter((l) => this.byId.has(l.source) && this.byId.has(l.target)).map((l) => {
      const key = l.source < l.target ? `${l.source}|${l.target}` : `${l.target}|${l.source}`;
      const i = pairs.get(key) ?? 0;
      pairs.set(key, i + 1);
      const dir = l.source < l.target ? 1 : -1;
      return { ...l, source: this.byId.get(l.source)!, target: this.byId.get(l.target)!, bend: i ? dir * Math.ceil(i / 2) * (i % 2 ? 0.18 : -0.18) : 0 };
    });
    if (this.nodeMesh.instanceMatrix.count < this.nodes.length) this.grow();
    this.hullDirty = true;
    const reanchor = this.anchor();
    if (sameTopo) {
      if (this.layout === "force" && reanchor) { if (this.still) this.settle(0.5); else if (!this.paused) this.sim.alpha(Math.max(this.sim.alpha(), 0.5)).restart(); }
      this.request();
      return;
    }
    const fresh = this.nodes.filter((n) => n.x === undefined);
    const now = performance.now();
    for (const id of this.born.keys()) if (!this.byId.has(id)) this.born.delete(id);
    if (this.effective === "full" && !this.still) for (const n of fresh) this.born.set(n.id, now);
    for (const n of fresh) {
      const nb = this.links.find((l) => (l.source === n && l.target.x !== undefined) || (l.target === n && l.source.x !== undefined));
      const a = nb ? (nb.source === n ? nb.target : nb.source) : null;
      if (a) { n.x = a.x! + (hash(n.id) - 0.5) * 60; n.y = a.y! + (hash(n.id + "y") - 0.5) * 60; n.z = (a.z ?? 0) + (hash(n.id + "z") - 0.5) * 60; } else seed(n);
    }
    this.sim.nodes(this.nodes);
    (this.sim.force("link") as any).links(this.links);
    if (this.layout !== "force") { this.place(kept > 0); if (!kept) this.fit(0); return; }
    if (!kept || this.still) { this.settle(kept ? 0.4 : 1); if (!kept) this.fit(0); }
    if (!this.still) { this.sim.alpha(kept ? 0.4 : this.sim.alpha()); if (!this.paused) this.sim.restart(); }
    this.request();
  }

  /** Más instancias de las que caben: se rehacen las mallas con sitio de sobra. */
  private grow() {
    const cap = Math.max(64, this.nodes.length * 2);
    for (const [k, m] of [["nodeMesh", this.nodeMat], ["arrows", this.arrows.material]] as const) {
      const prev = this[k];
      this.scene.remove(prev);
      prev.dispose();
      const next = new THREE.InstancedMesh(k === "nodeMesh" ? prev.geometry : this.cone, m as THREE.Material, k === "nodeMesh" ? cap : cap * 4);
      next.frustumCulled = false;
      next.count = 0;
      this.scene.add(next);
      this[k] = next;
    }
  }

  private settle(alpha: number) {
    this.sim.stop().alpha(alpha);
    const end = performance.now() + (this.still ? SETTLE_MS * 3 : SETTLE_MS);
    while (this.sim.alpha() > this.sim.alphaMin() && performance.now() < end) this.sim.tick();
    this.hullDirty = true;
  }

  /** Anclas de los halos en un anillo horizontal alrededor del centro, alternando arriba y abajo para usar la profundidad;
   * los halos que más nodos comparten van contiguos. Cada nodo va a la media de las anclas de sus halos. */
  private anchor(): boolean {
    const keys = this.layout === "force" ? this.halos.map((h) => h.key) : [];
    const sig = keys.join("|") + "#" + this.nodes.map((n) => (n.groups ?? []).join(",")).join(";");
    if (sig === this.anchorSig) return false;
    this.anchorSig = sig;
    if (keys.length) {
      const order = anchorOrder(this.nodes, keys);
      const r = order.length === 1 ? 0 : 120 + 30 * Math.sqrt(this.nodes.length);
      const at = new Map<string, [number, number, number]>();
      order.forEach((k, i) => { const a = (i * 2 * Math.PI) / order.length; at.set(k, [Math.cos(a) * r, order.length > 2 ? (i % 2 ? 0.3 : -0.3) * r : 0, Math.sin(a) * r]); });
      for (const n of this.nodes) {
        const ps = (n.groups ?? []).map((k) => at.get(k)).filter((q): q is [number, number, number] => !!q);
        if (ps.length) { [n.ax, n.ay, n.az] = [0, 1, 2].map((i) => ps.reduce((s, q) => s + q[i], 0) / ps.length); n.pull = PULL; }
        else { n.ax = 0; n.ay = -(r + 180); n.az = 0; n.pull = PULL_NONE * 2; }  // sin origen: zona neutra debajo
      }
    } else for (const n of this.nodes) { n.ax = 0; n.ay = 0; n.az = 0; n.pull = PULL_NONE; }
    (this.sim.force("link") as any).strength(keys.length ? LINK_WITH_HALOS : LINK);
    (this.sim.force("charge") as any).strength(keys.length ? CHARGE_WITH_HALOS : CHARGE);
    (this.sim.force("x") as any).x((d: SNode) => d.ax ?? 0);
    (this.sim.force("y") as any).y((d: SNode) => d.ay ?? 0);
    (this.sim.force("z") as any).z((d: SNode) => d.az ?? 0);
    return true;
  }

  setLayout(layout: Layout, root?: string) {
    if (layout === this.layout && root === this.root) return;
    const was = this.layout;
    this.layout = layout; this.root = root;
    if (!this.nodes.length) return;
    this.anchorSig = ""; this.anchor();
    if (layout === "force") {
      for (const n of this.nodes) { n.fx = null; n.fy = null; n.fz = null; n.pinned = false; }
      if (this.still) this.settle(0.6); else if (!this.paused) this.sim.alpha(0.6).restart();
    } else this.place(true);
    this.hullDirty = true;
    if (was !== layout) this.fit(this.still ? 0 : MORPH_MS + 200);
  }

  /** Radial o árbol: las posiciones del plano, con cada nivel un paso más al fondo (como el visor anterior). */
  private place(animate: boolean) {
    this.sim.stop().alpha(0);
    const p = placeLayout(this.layout, this.nodes, this.links.map((l) => ({ source: l.source.id, target: l.target.id })), this.root);
    const from = new Map<string, [number, number, number]>();
    for (const n of this.nodes) {
      const q = p.get(n.id)!;
      if (n.x !== undefined) from.set(n.id, [n.x, n.y!, n.z ?? 0]);
      n.fx = q.x; n.fy = -q.y; n.fz = -q.level * LEVEL_DEPTH; n.vx = n.vy = n.vz = 0; n.pinned = false;
      if (n.x === undefined || !animate || this.still) { n.x = n.fx; n.y = n.fy; n.z = n.fz; }
    }
    this.morph = animate && !this.still ? { from, start: performance.now() } : null;
    this.hullDirty = true;
    this.request();
  }

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

  /** Encuadra los nodos visibles (o los que cumplen `only`) sin cambiar el ángulo desde el que se miran. */
  fit(ms = 400, only?: (id: string) => boolean) {
    const ns = this.nodes.filter((n) => n.visible && n.x !== undefined && (!only || only(n.id)));
    if (!ns.length) return;
    if (!this.w) { this.pendingFit = () => this.fit(0, only); return; }
    const goal = () => {
      const box = new THREE.Box3();
      for (const n of ns) box.expandByPoint(pos(n));
      const c = box.getCenter(new THREE.Vector3());
      const r = ns.reduce((m, n) => Math.max(m, pos(n).distanceTo(c) + n.size), 0) + (this.halos.length ? HALO_PAD : 0);
      const fov = (this.camera.fov * Math.PI) / 360, aspect = Math.min(1, this.camera.aspect);
      const d = Math.max(only ? 120 : 80, (r / Math.sin(Math.atan(Math.tan(fov) * aspect))) * 1.05);
      const dir = this.camera.position.clone().sub(this.controls.target);
      if (dir.lengthSq() < 1e-6) dir.set(0, 0, 1);
      return { target: c, position: c.clone().add(dir.normalize().multiplyScalar(d)) };
    };
    cancelAnimationFrame(this.anim);
    const apply = (t: THREE.Vector3, p: THREE.Vector3) => { this.controls.target.copy(t); this.camera.position.copy(p); this.controls.update(); this.request(); };
    if (this.still || ms <= 0) { const g = goal(); apply(g.target, g.position); return; }
    const t0 = this.controls.target.clone(), p0 = this.camera.position.clone(), start = performance.now();
    const step = (now: number) => {
      const k = ease(Math.min(1, (now - start) / ms)), g = goal();
      apply(t0.clone().lerp(g.target, k), p0.clone().lerp(g.position, k));
      if (k < 1 || (this.moving() && now - start < FOLLOW_MS)) this.anim = requestAnimationFrame(step);
    };
    this.anim = requestAnimationFrame(step);
  }

  toPng(): string { this.draw(); return this.canvas.toDataURL("image/png"); }

  destroy() {
    this.sim.stop();
    cancelAnimationFrame(this.frame); cancelAnimationFrame(this.anim);
    this.cleanup.forEach((f) => f());
    this.controls.dispose();
    for (const h of this.haloObjs.values()) { h.mesh.geometry.dispose(); h.mat.dispose(); }
    for (const t of this.text.values()) t.tex.dispose();
    clearTimeout(this.focusTimer);
    for (const s of [...this.rings, ...this.pins, ...this.labels]) (s.material as THREE.SpriteMaterial).dispose();
    this.scene.traverse((o) => { const m = o as THREE.Mesh; if (m.geometry) m.geometry.dispose(); if (m.material) (Array.isArray(m.material) ? m.material : [m.material]).forEach((x) => x.dispose()); });
    this.ringTex.dispose(); this.pinTex.dispose(); this.sphere.dispose(); this.sphereLow.dispose();
    this.gl.dispose();
    this.gl.forceContextLoss();  // cada vuelta a 3D abriría otro contexto WebGL, y el navegador admite pocos
  }

  // --- interacción ---------------------------------------------------------------------------
  private pick(x: number, y: number) {
    this.ray.setFromCamera(new THREE.Vector2((x / this.w) * 2 - 1, -(y / this.h) * 2 + 1), this.camera);
    return this.ray;
  }

  private nodeAt(x: number, y: number): SNode | undefined {
    if (!this.drawn.length) return undefined;
    this.nodeMesh.boundingSphere = null;  // las instancias se movieron
    const hit = this.pick(x, y).intersectObject(this.nodeMesh, false).find((h) => h.instanceId !== undefined && this.drawn[h.instanceId]?.visible);
    return hit ? this.drawn[hit.instanceId!] : undefined;
  }

  private linkAt(x: number, y: number): SLink | undefined {
    const r = this.pick(x, y);
    r.params.Line = { threshold: Math.max(2, this.camera.position.distanceTo(this.controls.target) / 250) };
    const hits = r.intersectObjects([this.lines, this.dashes], false);
    const h = hits[0];
    if (!h || h.index === undefined) return undefined;
    return (h.object === this.lines ? this.lineOwner : this.dashOwner)[Math.floor(h.index / 2)];
  }

  /** El foco por señalar llega con retraso: pasar de largo por varios nodos no enciende ni apaga nada. */
  private aim(id: string | null) {
    clearTimeout(this.focusTimer);
    if (id === this.focusHover) return;
    this.focusTimer = window.setTimeout(() => { this.focusHover = id; this.request(); }, FOCUS_DELAY);
  }

  private setHover(id: string | null) {
    if (id === this.hover) return;
    this.hover = id; this.canvas.style.cursor = id ? "pointer" : "";
    this.aim(id && id !== "link" ? id : null);
    const n = id ? this.byId.get(id) : undefined;
    if (n) { const [sx, sy, px] = this.screen(n); this.events.hover?.(n.id, sx, sy - n.size * px); } else this.events.hover?.(null, 0, 0);
    this.request();
  }

  /** Posición en pantalla de un nodo y cuántos píxeles mide una unidad del mundo a su distancia. */
  private screen(n: SNode): [number, number, number] {
    const v = pos(n), d = v.distanceTo(this.camera.position);
    v.project(this.camera);
    return [(v.x + 1) / 2 * this.w, (1 - v.y) / 2 * this.h, this.h / (2 * d * Math.tan((this.camera.fov * Math.PI) / 360))];
  }

  private onDown(ev: PointerEvent) {
    if (ev.button !== 0) return;
    this.down = { x: ev.offsetX, y: ev.offsetY };
    const n = this.nodeAt(ev.offsetX, ev.offsetY);
    if (!n) return;
    this.controls.enabled = false;
    this.canvas.setPointerCapture(ev.pointerId);
    const normal = this.camera.getWorldDirection(new THREE.Vector3());
    this.drag = { node: n, plane: new THREE.Plane().setFromNormalAndCoplanarPoint(normal, pos(n)), moved: false, x0: ev.offsetX, y0: ev.offsetY };
  }

  private onMove(ev: PointerEvent) {
    const d = this.drag;
    if (d) {
      if (!d.moved && Math.hypot(ev.offsetX - d.x0, ev.offsetY - d.y0) < CLICK_SLOP) return;
      const sim = this.layout === "force" && !this.paused;
      if (!d.moved) { d.moved = true; if (sim) this.sim.alphaTarget(0.3).restart(); }
      const p = this.pick(ev.offsetX, ev.offsetY).ray.intersectPlane(d.plane, new THREE.Vector3());
      if (!p) return;
      d.node.fx = p.x; d.node.fy = p.y; d.node.fz = p.z;
      if (!sim) { d.node.x = p.x; d.node.y = p.y; d.node.z = p.z; this.hullDirty = true; }
      this.request();
      return;
    }
    if (ev.buttons) return;  // girando o moviendo la cámara
    const n = this.nodeAt(ev.offsetX, ev.offsetY);
    this.setHover(n?.id ?? (this.linkAt(ev.offsetX, ev.offsetY) ? "link" : null));
  }

  private onUp(ev: PointerEvent) {
    const d = this.drag, down = this.down;
    this.drag = null; this.down = null; this.controls.enabled = true;
    if (d) {
      if (this.canvas.hasPointerCapture(ev.pointerId)) this.canvas.releasePointerCapture(ev.pointerId);
      if (d.moved) { this.release(d.node); return; }
      this.events.nodeClick?.(d.node.id);
      return;
    }
    if (ev.button !== 0 || !down || Math.hypot(ev.offsetX - down.x, ev.offsetY - down.y) >= CLICK_SLOP) return;  // fue un giro de la cámara
    const l = this.linkAt(ev.offsetX, ev.offsetY);
    if (l) this.events.linkClick?.(l.id); else this.events.backgroundClick?.();
  }

  private endDrag() {
    const d = this.drag;
    this.drag = null; this.down = null; this.controls.enabled = true;
    if (d?.moved) this.release(d.node);
  }

  /** Fin de un arrastre: el nodo se queda donde se soltó. En fuerza queda fijado (con una marca) hasta un doble clic o «Restablecer posiciones». */
  private release(n: SNode) {
    if (this.layout !== "force") return;
    n.pinned = true; this.sim.alphaTarget(0); this.request();
  }

  private unpin(ns: SNode[]) {
    for (const n of ns) { n.fx = null; n.fy = null; n.fz = null; n.pinned = false; }
    if (this.still || this.paused) this.settle(0.5); else this.sim.alpha(Math.max(this.sim.alpha(), 0.5)).restart();
    this.hullDirty = true;
    this.request();
  }

  resetPositions() {
    if (this.layout === "force") this.unpin(this.nodes.filter((n) => n.pinned)); else this.place(true);
    this.fit(this.still ? 0 : MORPH_MS + 200);
  }

  // --- dibujo --------------------------------------------------------------------------------
  private request() {
    if (!this.frame) this.frame = requestAnimationFrame(() => { this.frame = 0; this.draw(); });
  }

  private color(c: string) { let x = this.colors.get(c); if (!x) { x = new THREE.Color(c); this.colors.set(c, x); } return x; }

  private linkVisible(l: SLink) { return l.visible && l.source.visible && l.target.visible && l.source.x !== undefined; }

  /** Punto de una arista en `q` ∈ [0, 1]: recta, o curva cuadrática si hay varias entre los mismos nodos. */
  private along(l: SLink, q: number, out = new THREE.Vector3()) {
    const a = pos(l.source), b = pos(l.target);
    if (!l.bend) return out.copy(a).lerp(b, q);
    const d = b.clone().sub(a), side = d.clone().cross(new THREE.Vector3(0, 1, 0));
    if (side.lengthSq() < 1e-6) side.set(1, 0, 0);
    const c = a.clone().add(b).multiplyScalar(0.5).add(side.normalize().multiplyScalar(d.length() * l.bend));
    const r = 1 - q;
    return out.set(r * r * a.x + 2 * r * q * c.x + q * q * b.x, r * r * a.y + 2 * r * q * c.y + q * q * b.y, r * r * a.z + 2 * r * q * c.z + q * q * b.z);
  }

  private draw() {
    if (!this.w) return;
    const now = performance.now();
    this.measure(now);
    const full = this.effective === "full";
    let animating = false;
    if (this.morph) {
      const k = ease(Math.min(1, (now - this.morph.start) / MORPH_MS));
      for (const n of this.nodes) { const f = this.morph.from.get(n.id); if (f && n.fx != null) { n.x = f[0] + (n.fx - f[0]) * k; n.y = f[1] + (n.fy! - f[1]) * k; n.z = f[2] + (n.fz! - f[2]) * k; } }
      this.hullDirty = true;
      if (k >= 1) this.morph = null; else animating = true;
    }
    const cap = full ? MAX_LABELS : MAX_LABELS_REDUCED;
    const links = this.links.filter((l) => this.linkVisible(l));
    // como en 2D: el foco por señalar llega con retraso y se atenúa con un fundido; con «Reducido» o menos movimiento, solo lo seleccionado
    const calm = !full || this.still;
    const hoverNode = !calm && this.focusHover && this.byId.has(this.focusHover) ? this.focusHover : null;
    const focusId = [hoverNode, this.selectedNode].find((id) => id && this.byId.get(id)?.visible) ?? null;  // un nodo oculto por un filtro no hace de foco
    const near = new Set<string>();
    if (focusId) { near.add(focusId); for (const l of links) if (l.source.id === focusId || l.target.id === focusId) { near.add(l.source.id); near.add(l.target.id); } }
    const touches = (l: SLink) => !focusId || l.source.id === focusId || l.target.id === focusId;
    const dt = now - this.fadeAt > 100 ? 16 : now - this.fadeAt, step = dt / FADE_MS;
    this.fadeAt = now;
    const toward = (cur: number | undefined, to: number) => { const c = cur ?? 1; if (c === to) return c; animating = true; return c < to ? Math.min(to, c + step) : Math.max(to, c - step); };
    this.haloLit = toward(this.haloLit, focusId ? 0 : 1);
    for (const n of this.nodes) n.lit = toward(n.lit, !focusId || near.has(n.id) ? 1 : 0);
    for (const l of links) l.lit = toward(l.lit, touches(l) ? 1 : 0);
    const tint = (c: string, alpha: number, out: THREE.Color) => out.copy(this.color(c)).lerp(this.bg, 1 - alpha);
    const camUp = new THREE.Vector3(0, 1, 0).applyQuaternion(this.camera.quaternion);
    const tmp = new THREE.Color(), m = new THREE.Matrix4(), q = new THREE.Quaternion(), v = new THREE.Vector3(), sc = new THREE.Vector3();

    // nodos: los nuevos entran creciendo; fuera del foco, apagados hacia el fondo
    this.drawn = [];
    const named: { n: SNode; px: number; d: number }[] = [];
    let ringCount = 0, pinCount = 0;
    const camRight = new THREE.Vector3(1, 0, 0).applyQuaternion(this.camera.quaternion);
    const ring = (n: SNode, r: number, color: string) => {
      let s = this.rings[ringCount];
      if (!s) { s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.ringTex, transparent: true, alphaTest: 0.1, depthWrite: false })); this.rings.push(s); this.scene.add(s); }
      (s.material as THREE.SpriteMaterial).color.set(color);
      s.position.copy(pos(n)); s.scale.setScalar(r * 2 * (64 / 54)); s.visible = true;
      ringCount++;
    };
    for (const n of this.nodes) {
      if (!n.visible || n.x === undefined) continue;
      const b = this.born.get(n.id);
      let e = 1;
      if (b !== undefined) { e = Math.min(1, (now - b) / ENTER_MS); if (e >= 1) this.born.delete(n.id); else animating = true; e = 1 - Math.pow(1 - e, 3); }
      const lit = n.lit ?? 1, alpha = (DIM + (1 - DIM) * lit) * e;
      const r = n.size * (0.4 + 0.6 * e);
      m.compose(pos(n), q.identity(), sc.setScalar(r));
      this.nodeMesh.setMatrixAt(this.drawn.length, m);
      this.nodeMesh.setColorAt(this.drawn.length, tint(n.color, alpha, tmp));
      this.drawn.push(n);
      const sel = n.id === this.selectedNode, hov = n.id === this.hover;
      if (sel) ring(n, r + 3, CANVAS.selected); else if (hov) ring(n, r + 2.5, CANVAS.foreground); else if (n.ring && lit > 0.5) ring(n, r + 3, CANVAS.foreground);
      if (n.pinned) {  // fijado al arrastrarlo: un punto en el borde (doble clic lo suelta)
        let s = this.pins[pinCount];
        if (!s) { s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.pinTex, transparent: true, alphaTest: 0.1, depthWrite: false })); this.pins.push(s); this.scene.add(s); }
        s.position.copy(pos(n)).addScaledVector(camUp, r * 0.75).addScaledVector(camRight, r * 0.75); s.scale.setScalar(Math.max(3, r * 0.6)); s.visible = true;
        pinCount++;
      }
      if (near.has(n.id) || lit > 0.02) { const [, , px] = this.screen(n); named.push({ n, px, d: pos(n).distanceTo(this.camera.position) }); }
    }
    const geo = full ? this.sphere : this.sphereLow;
    if (this.nodeMesh.geometry !== geo) this.nodeMesh.geometry = geo;
    this.nodeMesh.count = this.drawn.length;
    this.nodeMesh.instanceMatrix.needsUpdate = true;
    if (this.nodeMesh.instanceColor) this.nodeMesh.instanceColor.needsUpdate = true;
    for (let i = ringCount; i < this.rings.length; i++) this.rings[i].visible = false;
    for (let i = pinCount; i < this.pins.length; i++) this.pins[i].visible = false;

    // aristas: tramos rectos (o curvas en varios tramos), las invalidadas discontinuas; flecha en el borde del destino
    const solid: number[] = [], solidC: number[] = [], dash: number[] = [], dashC: number[] = [], dashD: number[] = [];
    this.lineOwner = []; this.dashOwner = [];
    let arrowCount = 0;
    const up = new THREE.Vector3(0, 1, 0), a0 = new THREE.Vector3(), a1 = new THREE.Vector3();
    const base = links.length > MANY_LINKS ? 0.32 : 0.55;  // con cientos de aristas, más tenues: solo las del foco se leen claras
    for (const l of links) {
      const sel = l.id === this.selectedLink;
      const on = focusId && touches(l) ? (l.strong ? 1 : 0.85) : l.strong ? Math.min(1, base + 0.35) : base;  // más brillo para lo respaldado por varios orígenes
      const alpha = sel ? 1 : DIM * 0.5 + (on - DIM * 0.5) * (l.lit ?? 1);
      const c = tint(sel ? CANVAS.selected : l.color, alpha, tmp);
      const steps = l.bend ? CURVE : 1;
      for (let i = 0; i < steps; i++) {
        this.along(l, i / steps, a0); this.along(l, (i + 1) / steps, a1);
        if (l.dashed) { dash.push(a0.x, a0.y, a0.z, a1.x, a1.y, a1.z); dashC.push(c.r, c.g, c.b, c.r, c.g, c.b); dashD.push(0, a0.distanceTo(a1)); this.dashOwner.push(l); }
        else { solid.push(a0.x, a0.y, a0.z, a1.x, a1.y, a1.z); solidC.push(c.r, c.g, c.b, c.r, c.g, c.b); this.lineOwner.push(l); }
      }
      if (arrowCount < this.arrows.instanceMatrix.count) {
        const tip = pos(l.target), from = this.along(l, 0.9, a0), dir = tip.clone().sub(from).normalize();
        v.copy(tip).addScaledVector(dir, -(l.target.size + 1));
        m.compose(v, q.setFromUnitVectors(up, dir), sc.set(2.2, 7, 2.2));
        this.arrows.setMatrixAt(arrowCount, m);
        this.arrows.setColorAt(arrowCount, c);
        arrowCount++;
      }
    }
    const fill = (o: THREE.LineSegments, p: number[], c: number[], d?: number[]) => {
      const g = o.geometry, n = p.length / 3;
      if ((g.getAttribute("position") as THREE.BufferAttribute).count < n) {
        g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 6), 3));
        g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(n * 6), 3));
        if (d) g.setAttribute("lineDistance", new THREE.BufferAttribute(new Float32Array(n * 2), 1));
      }
      (g.getAttribute("position") as THREE.BufferAttribute).set(p); g.getAttribute("position").needsUpdate = true;
      (g.getAttribute("color") as THREE.BufferAttribute).set(c); g.getAttribute("color").needsUpdate = true;
      if (d) { (g.getAttribute("lineDistance") as THREE.BufferAttribute).set(d); g.getAttribute("lineDistance").needsUpdate = true; }
      g.setDrawRange(0, n);
      g.boundingSphere = null;
    };
    fill(this.lines, solid, solidC);
    fill(this.dashes, dash, dashC, dashD);
    this.arrows.count = arrowCount;
    this.arrows.instanceMatrix.needsUpdate = true;
    if (this.arrows.instanceColor) this.arrows.instanceColor.needsUpdate = true;

    // partículas: solo en las aristas válidas del nodo señalado, y solo mientras se señala
    const pp = this.particles.geometry.getAttribute("position") as THREE.BufferAttribute;
    let pc = 0;
    if (hoverNode) {  // lentas, pequeñas y discretas, y entran con el mismo fundido que el foco
      for (const l of links.filter((x) => !x.dashed && touches(x)).slice(0, 60)) {
        this.along(l, (now / PARTICLE_MS + hash(l.id)) % 1, v);
        pp.setXYZ(pc++, v.x, v.y, v.z);
      }
      (this.particles.material as THREE.PointsMaterial).opacity = 0.45 * (1 - this.haloLit);
      animating ||= pc > 0;
    }
    pp.needsUpdate = true;
    this.particles.geometry.setDrawRange(0, pc);

    // textos: nombres de los nodos más cercanos a la cámara y tipo de relación de las aristas, con el mismo tope que en 2D
    let used = 0;
    const label = (txt: string, color: string, at: THREE.Vector3, px: number, below = 0, opacity = 1, min = 0): THREE.Sprite | undefined => {
      const hpx = Math.max(min, Math.min(TEXT_PX, TEXT_PX * px));  // cerca, tamaño fijo; lejos, encoge con la distancia
      if (hpx < MIN_TEXT_PX) return;
      const t = this.textTex(txt, color);
      let s = this.labels[used];
      if (!s) { s = new THREE.Sprite(new THREE.SpriteMaterial({ transparent: true, depthTest: false, depthWrite: false })); s.renderOrder = 10; this.labels.push(s); this.scene.add(s); }
      const mat = s.material as THREE.SpriteMaterial;
      if (mat.map !== t.tex) { mat.map = t.tex; mat.needsUpdate = true; }
      mat.opacity = opacity;
      const hw = hpx / px;  // alto en unidades del mundo
      s.scale.set(hw * t.aspect, hw, 1);
      s.position.copy(at).addScaledVector(camUp, below >= 0 ? -below - hw / 2 : -below + hw / 2);  // `below` negativo: por encima
      s.visible = true;
      used++;
      return s;
    };
    // como en 2D: de lejos, sin nombres salvo el del nodo señalado o seleccionado; de cerca, los más próximos a la cámara
    const own = (n: SNode) => n.id === this.selectedNode || n.id === this.hover;
    const shown = named.filter((x) => own(x.n) || x.px >= CAPTION_PX).sort((a, b) => Number(own(b.n)) - Number(own(a.n)) || a.d - b.d).slice(0, cap);
    for (const { n, px } of shown) {
      const focus = own(n);
      label(!focus && n.caption.length > 24 ? n.caption.slice(0, 23) + "…" : n.caption, CANVAS.foreground, pos(n), px, n.size + 2, focus ? 1 : n.lit ?? 1, focus ? TEXT_PX : 0);
    }
    // tipo de relación: solo de lo enfocado o seleccionado (en 3D, con todas, los rótulos tapan el grafo)
    const rel = links.filter((l) => l.label && (l.id === this.selectedLink || (focusId && touches(l))));
    for (const l of rel.slice(0, cap)) {
      const mid = this.along(l, 0.5), d = mid.distanceTo(this.camera.position);
      const px = this.h / (2 * d * Math.tan((this.camera.fov * Math.PI) / 360));
      label(l.label.length > 28 ? l.label.slice(0, 27) + "…" : l.label, l.id === this.selectedLink ? CANVAS.selected : CANVAS.label, mid, px, -6 / px);
    }

    // halos: solo en la disposición de fuerza
    const halosOn = this.layout === "force";
    const placed: [number, number, number][] = [];  // rótulos de halo ya puestos (centro y ancho en pantalla): dos halos con la misma cima no se pisan
    if (halosOn && this.hullDirty && (!animating && !this.moving() || now - this.hullAt > HALO_EVERY)) { this.hulls(); this.hullAt = now; this.hullDirty = false; }
    if (halosOn && this.hullDirty) animating = true;  // falta recalcularla cuando pare
    for (const [k, h] of this.haloObjs) {
      const on = halosOn && !!h.mesh.userData.ok;
      h.mesh.visible = on;
      if (!on) continue;
      const fade = 0.35 + 0.65 * this.haloLit, halo = this.halos.find((x) => x.key === k);
      h.mat.uniforms.opacity.value = HALO_ALPHA * fade;
      const top = h.mesh.userData.top as THREE.Vector3, name = halo?.name ?? k;  // nombre sobre la cima del volumen
      const d = top.distanceTo(this.camera.position), px = this.h / (2 * d * Math.tan((this.camera.fov * Math.PI) / 360));
      const txt = `${name.length > 22 ? name.slice(0, 21) + "…" : name} · ${h.mesh.userData.count}`, s0 = top.clone().project(this.camera);
      const sx = (s0.x + 1) / 2 * this.w, lw = TEXT_PX * this.textTex(txt, halo?.color ?? CANVAS.foreground).aspect;
      let sy = (1 - s0.y) / 2 * this.h, up = 4;
      while (placed.some(([x, y, w]) => Math.abs(x - sx) < (w + lw) / 2 + 4 && Math.abs(y - (sy - up)) < TEXT_PX + 2)) up += TEXT_PX + 2;
      placed.push([sx, sy - up, lw]);
      label(txt, halo?.color ?? CANVAS.foreground, top, px, -up / px, fade, TEXT_PX);  // el nombre del halo se lee siempre
    }
    for (let i = used; i < this.labels.length; i++) this.labels[i].visible = false;

    this.gl.render(this.scene, this.camera);
    if (animating) this.request();
  }

  /** Volumen de cada halo: envolvente convexa de puntos alrededor de sus nodos visibles, con normales suaves para el contorno. */
  private hulls() {
    const keys = new Set(this.halos.map((h) => h.key));
    for (const [k, h] of this.haloObjs) if (!keys.has(k)) { this.scene.remove(h.mesh); h.mesh.geometry.dispose(); h.mat.dispose(); this.haloObjs.delete(k); }
    for (const h of this.halos) {
      let o = this.haloObjs.get(h.key);
      if (!o) {
        const mat = new THREE.ShaderMaterial({ uniforms: { color: { value: new THREE.Color(h.color) }, opacity: { value: HALO_ALPHA } }, vertexShader: HALO_VERTEX, fragmentShader: HALO_FRAGMENT,
          transparent: true, depthWrite: false, side: THREE.DoubleSide });
        o = { mesh: new THREE.Mesh(new THREE.BufferGeometry(), mat), mat };
        o.mesh.renderOrder = 5;
        this.scene.add(o.mesh);
        this.haloObjs.set(h.key, o);
      }
      (o.mat.uniforms.color.value as THREE.Color).set(h.color);
      const ns = this.nodes.filter((n) => n.visible && n.x !== undefined && n.groups?.includes(h.key));
      o.mesh.userData.ok = ns.length >= 2;
      if (ns.length < 2) continue;
      const pts: THREE.Vector3[] = [];
      let top = new THREE.Vector3(0, -Infinity, 0);
      for (const n of ns) for (const d of ICO) {
        const p = pos(n).addScaledVector(d, n.size + HALO_PAD);
        pts.push(p);
        if (p.y > top.y) top = p;
      }
      let g: THREE.BufferGeometry = new ConvexGeometry(pts);
      g.deleteAttribute("normal"); g.deleteAttribute("uv");
      g = mergeVertices(g);
      g.computeVertexNormals();
      o.mesh.geometry.dispose();
      o.mesh.geometry = g;
      o.mesh.userData = { ok: true, top, count: ns.length };
    }
  }

  /** Textura con un texto con contorno del color del fondo, para que se lea sobre cualquier cosa. Se reutiliza por texto y color. */
  private textTex(txt: string, color: string) {
    const key = `${color}|${txt}`;
    let t = this.text.get(key);
    if (t) return t;
    if (this.text.size > TEXT_CACHE) { for (const x of this.text.values()) x.tex.dispose(); this.text.clear(); }
    const c = document.createElement("canvas"), x = c.getContext("2d")!;
    x.font = `${FONT_PX}px ${FONT}`;
    const w = Math.ceil(x.measureText(txt).width) + 12, h = FONT_PX + 12;
    c.width = w; c.height = h;
    x.font = `${FONT_PX}px ${FONT}`; x.textAlign = "center"; x.textBaseline = "middle";
    x.lineWidth = 6; x.strokeStyle = CANVAS.background; x.lineJoin = "round"; x.strokeText(txt, w / 2, h / 2);
    x.fillStyle = color; x.fillText(txt, w / 2, h / 2);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace; tex.minFilter = THREE.LinearFilter; tex.generateMipmaps = false;
    t = { tex, aspect: w / h };
    this.text.set(key, t);
    return t;
  }

  /** Igual que en 2D: si los fotogramas van lentos de forma sostenida, el automático baja a reducido; si aun así sigue lento
   * (o el modo es fijo), se avisa una vez para sugerir volver a 2D. */
  private measure(now: number) {
    const dt = now - this.lastDraw;
    this.lastDraw = now;
    if (dt > 250) return;
    this.slow = dt > SLOW_MS ? this.slow + 1 : Math.max(0, this.slow - 2);
    if (this.slow < SLOW_FRAMES) return;
    this.slow = 0;
    if (this.mode === "auto" && this.effective === "full") { this.autoDown = true; this.applyEffects(); }
    else if (!this.slowSaid) { this.slowSaid = true; this.events.slow?.(); }
  }
}
