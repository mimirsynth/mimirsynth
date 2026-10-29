/** Disposiciones del grafo compartidas por el lienzo 2D y el 3D: fuerza (con anclas por origen), radial y árbol. */
export type Layout = "force" | "radial" | "tree";

type Node = { id: string; size: number; groups?: string[] };
type Link = { source: string; target: string };
/** Posición fija de un nodo en las disposiciones colocadas (radial y árbol) y su nivel desde la raíz. */
export type Placed = { x: number; y: number; level: number };

const LEVEL = 110;      // distancia entre niveles
const SPACING = 14;     // hueco mínimo entre nodos vecinos del mismo nivel

/** Hash estable de un id → [0, 1): la posición inicial no depende del orden en que llegan los datos. */
export function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return ((h >>> 0) % 100000) / 100000;
}

/** Orden de los halos en el círculo de anclas: cadena voraz en la que cada uno va junto al que más nodos comparte con el anterior. */
export function anchorOrder(nodes: Node[], keys: string[]): string[] {
  if (!keys.length) return [];
  const shared = new Map<string, number>();
  for (const n of nodes) {
    const g = (n.groups ?? []).filter((k) => keys.includes(k));
    for (let i = 0; i < g.length; i++) for (let j = i + 1; j < g.length; j++) for (const k of [`${g[i]}|${g[j]}`, `${g[j]}|${g[i]}`]) shared.set(k, (shared.get(k) ?? 0) + 1);
  }
  const order = [keys[0]], left = keys.slice(1);
  while (left.length) {
    const last = order[order.length - 1];
    let bi = 0;
    left.forEach((k, i) => { if ((shared.get(`${last}|${k}`) ?? 0) > (shared.get(`${last}|${left[bi]}`) ?? 0)) bi = i; });
    order.push(left.splice(bi, 1)[0]);
  }
  return order;
}

/** Jerarquía para radial y árbol: raíces = nodos sin aristas entrantes (o el de más salientes si todo es ciclo, o `root` si se pide);
 * cada nodo cuelga del primero que lo alcanza siguiendo las aristas en su sentido. Los que no se alcanzan son raíces nuevas.
 * Devuelve las raíces, los hijos de cada nodo en el árbol, su nivel y su anchura (hojas del subárbol). */
function hierarchy(nodes: Node[], links: Link[], root?: string) {
  const out = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  const incoming = new Map<string, number>(nodes.map((n) => [n.id, 0]));
  for (const l of links) {
    if (!out.has(l.source) || !out.has(l.target) || l.source === l.target) continue;
    out.get(l.source)!.push(l.target);
    incoming.set(l.target, incoming.get(l.target)! + 1);
  }
  const byId = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);  // orden estable: no depende del orden de llegada
  for (const cs of out.values()) cs.sort(byId);
  let roots = root && out.has(root) ? [root] : nodes.filter((n) => !incoming.get(n.id)).map((n) => n.id).sort(byId);
  if (!roots.length && nodes.length) roots = [nodes.reduce((a, b) => (out.get(b.id)!.length > out.get(a.id)!.length ? b : a)).id];
  const level = new Map<string, number>(), children = new Map<string, string[]>(), queue: string[] = [];
  const visit = (r: string) => {
    level.set(r, 0); children.set(r, []); queue.push(r);
    for (let i = queue.length - 1; i < queue.length; i++) {
      const id = queue[i];
      for (const c of out.get(id)!) {
        if (level.has(c)) continue;
        level.set(c, level.get(id)! + 1); children.set(c, []); children.get(id)!.push(c); queue.push(c);
      }
    }
  };
  roots.forEach(visit);
  for (const n of [...nodes].sort((a, b) => byId(a.id, b.id))) if (!level.has(n.id)) { roots.push(n.id); visit(n.id); }  // inalcanzables
  const width = new Map<string, number>();
  for (let i = queue.length - 1; i >= 0; i--) { const cs = children.get(queue[i])!; width.set(queue[i], cs.length ? cs.reduce((a, c) => a + width.get(c)!, 0) : 1); }
  return { roots, children, level, width };
}

/** Árbol de arriba abajo: cada hoja ocupa una franja y cada padre queda centrado sobre sus hijos. */
export function treeLayout(nodes: Node[], links: Link[], root?: string): Map<string, Placed> {
  const { roots, children, level, width } = hierarchy(nodes, links, root);
  const big = nodes.reduce((m, n) => Math.max(m, n.size), 0);
  const gap = Math.max(60, big * 2 + SPACING), step = Math.max(LEVEL, big * 2 + SPACING);
  const pos = new Map<string, Placed>();
  const place = (id: string, x0: number): number => {
    const cs = children.get(id)!;
    let x = x0 + 0.5;
    if (cs.length) { let o = x0; const xs = cs.map((c) => { const r = place(c, o); o += width.get(c)!; return r; }); x = (xs[0] + xs[xs.length - 1]) / 2; }
    pos.set(id, { x, y: level.get(id)! * step, level: level.get(id)! });
    return x;
  };
  let o = 0;
  for (const r of roots) { place(r, o); o += width.get(r)!; }
  for (const p of pos.values()) p.x = (p.x - o / 2) * gap;
  return pos;
}

/** Radial: la raíz (o las raíces) en el centro y cada nivel en un anillo; cada subárbol recibe un arco proporcional a su anchura,
 * y el radio de cada anillo crece hasta que sus nodos no se pisan. */
export function radialLayout(nodes: Node[], links: Link[], root?: string): Map<string, Placed> {
  const { roots, children, level, width } = hierarchy(nodes, links, root);
  const size = new Map(nodes.map((n) => [n.id, n.size]));
  const angle = new Map<string, number>();
  const assign = (id: string, a0: number, span: number) => {
    const cs = children.get(id)!, w = width.get(id)!;
    let o = a0;
    for (const c of cs) { const s = (width.get(c)! / w) * span; angle.set(c, o + s / 2); assign(c, o, s); o += s; }
  };
  const total = roots.reduce((a, r) => a + width.get(r)!, 0);
  let o = 0;
  for (const r of roots) { const s = (width.get(r)! / total) * Math.PI * 2; angle.set(r, o + s / 2); assign(r, o, s); o += s; }
  // radio de cada nivel: al menos un paso más que el anterior y lo bastante grande para el hueco angular más estrecho del anillo
  const rings = new Map<number, string[]>();
  for (const [id, l] of level) (rings.get(l) ?? rings.set(l, []).get(l)!).push(id);
  const radius = new Map<number, number>();
  const levels = [...rings.keys()].sort((a, b) => a - b);
  let prev = 0;
  for (const l of levels) {
    const ids = rings.get(l)!.sort((a, b) => angle.get(a)! - angle.get(b)!);
    const big = ids.reduce((m, id) => Math.max(m, size.get(id)!), 0);
    let need = l === 0 && ids.length === 1 ? 0 : prev + LEVEL;
    if (ids.length > 1) {
      let narrow = Math.PI * 2;
      ids.forEach((id, i) => { const nx = ids[(i + 1) % ids.length]; let d = angle.get(nx)! - angle.get(id)!; if (d <= 0) d += Math.PI * 2; narrow = Math.min(narrow, d); });
      need = Math.max(need, (big * 2 + SPACING) / Math.max(narrow, 1e-3));
    }
    radius.set(l, need); prev = need;
  }
  const pos = new Map<string, Placed>();
  for (const [id, l] of level) { const r = radius.get(l)!, a = angle.get(id)! - Math.PI / 2; pos.set(id, { x: Math.cos(a) * r, y: Math.sin(a) * r, level: l }); }
  return pos;
}

export function placeLayout(layout: Layout, nodes: Node[], links: Link[], root?: string) {
  return layout === "tree" ? treeLayout(nodes, links, root) : radialLayout(nodes, links, root);
}
