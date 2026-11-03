import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Btn, CANVAS, GraphCanvas, typeColor, type CanvasLink, type CanvasNode, type GraphCanvasHandle } from "../ui";

type Other = { uuid: string; name: string; labels: string[] };
type GroupFacts = { relation: string; direction: "out" | "in"; current: { other: Other }[]; previous: { other: Other }[] };
export const MINI_NEIGHBORS = 12;  // neighbours drawn; the page already sorts them by current facts, then by facts
const MINI_LABELS = 3;             // edges whose label is always drawn (those with most facts); the others show it on hover
/** A relation name as words: `HOSTED_ON` and `HostedOn` read «hosted on». */
export const humanRelation = (name: string) => name.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/_+/g, " ").trim().toLowerCase();

/** The entity and its neighbours at depth 1 (issue 194), with the Graph's own renderer: the entity in the centre, the neighbours with the
 *  most current facts around it, coloured by type, and one edge per neighbour with its most frequent relation and how many facts join
 *  them. A click on a neighbour opens its page (on a phone the first tap names it, the second opens it); «Expand» opens the Graph. */
export default function EntityMiniGraph({ entity, groups, neighbors, link, expand }: {
  entity: Other; groups: GroupFacts[]; neighbors: (Other & { facts: number; current: number })[]; link: (o: Other) => string; expand?: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const phone = useMediaQuery("(max-width: 48em)");
  const [picked, setPicked] = useState<string | null>(null);
  const shown = neighbors.slice(0, MINI_NEIGHBORS);
  // the box changes size with the window (and from desktop to phone): fit the graph again, or part of it falls outside
  const box = useRef<HTMLDivElement>(null);
  const gc = useRef<GraphCanvasHandle>(null);
  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(() => requestAnimationFrame(() => gc.current?.fit(0)));  // after the canvas has taken the new size
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);
  const { nodes, links } = useMemo(() => {
    const color = (labels: string[]) => typeColor(labels[0]);  // the same colour per type as the Graph and the entity chips
    // per neighbour: how many facts in each direction and relation, and whether any is current
    const pairs = new Map<string, { out: number; in: number; rels: Map<string, number>; current: boolean }>();
    for (const g of groups) {
      for (const [list, current] of [[g.current, true], [g.previous, false]] as const) {
        for (const f of list) {
          const p = pairs.get(f.other.uuid) ?? { out: 0, in: 0, rels: new Map(), current: false };
          p[g.direction] += 1; p.rels.set(g.relation, (p.rels.get(g.relation) ?? 0) + 1); p.current ||= current;
          pairs.set(f.other.uuid, p);
        }
      }
    }
    const top = (p: { rels: Map<string, number> }) => [...p.rels.entries()].sort((a, b) => b[1] - a[1]);
    const nodes: CanvasNode[] = [{ id: entity.uuid, color: color(entity.labels), size: 11, caption: entity.name, visible: true,
      tooltip: [entity.name, entity.labels.join(", ")].filter(Boolean).join("\n") }];
    const links: CanvasLink[] = [];
    for (const n of shown) {
      const p = pairs.get(n.uuid);
      const rels = p ? top(p) : [];
      nodes.push({ id: n.uuid, color: color(n.labels), size: 6, caption: n.name, visible: true,
        tooltip: [n.name, ...rels.map(([r, c]) => `${humanRelation(r)}${c > 1 ? ` ×${c}` : ""}`)].join("\n") });
      if (!p) continue;
      const total = p.out + p.in;
      const label = `${humanRelation(rels[0][0])}${rels.length > 1 ? " +" : ""}${total > 1 ? ` ×${total}` : ""}`;
      const [source, target] = p.out >= p.in ? [entity.uuid, n.uuid] : [n.uuid, entity.uuid];
      links.push({ id: `mini-${n.uuid}`, source, target, label, color: p.current ? CANVAS.link : CANVAS.linkInvalid, dashed: !p.current, visible: true, strong: total > 1 });
    }
    // labels collide when there are many neighbours: only the strongest edges keep theirs; the rest show it on hover (issue 200)
    const strength = (l: CanvasLink) => { const p = pairs.get(l.source === entity.uuid ? l.target : l.source); return p ? p.out + p.in : 0; };
    const loud = new Set([...links].sort((a, b) => strength(b) - strength(a)).slice(0, MINI_LABELS).map((l) => l.id));
    for (const l of links) l.quiet = !loud.has(l.id);
    return { nodes, links };
  }, [entity, groups, shown]);  // eslint-disable-line react-hooks/exhaustive-deps
  const open = (id: string) => { const o = shown.find((n) => n.uuid === id); if (o) navigate(link(o)); };
  const click = (id: string) => {
    if (id === entity.uuid) return;
    if (phone && picked !== id) { setPicked(id); return; }  // on a phone the first tap names the neighbour; the second opens it
    open(id);
  };
  const pickedNode = shown.find((n) => n.uuid === picked);
  if (!neighbors.length) return null;
  return (
    <Stack gap={4}>
      <Group justify="space-between" gap="xs">
        <Text size="sm" fw={700}>{t("Relacionadas ({{count}})", { count: neighbors.length })}</Text>
        {expand && <Btn size="row" icon="graph" component={Link} to={expand}>{t("Ampliar")}</Btn>}
      </Group>
      <div ref={box} className="ms-minigraph" role="img" aria-label={t("Grafo de {{name}} y {{count}} entidades relacionadas", { name: entity.name, count: shown.length })}>
        <GraphCanvas ref={gc} nodes={nodes} links={links} layout="force" effects="reduced" selectedNode={picked} onNodeClick={click} onBackgroundClick={() => setPicked(null)} />
      </div>
      {pickedNode && <Text size="xs"><Link to={link(pickedNode)}>{t("Abrir {{name}}", { name: pickedNode.name })}</Link></Text>}
      {neighbors.length > shown.length && <Text size="xs" c="dimmed">{t("y {{count}} más", { count: neighbors.length - shown.length })}</Text>}
      {/* the same neighbours as links, for the keyboard and screen readers: the canvas is not reachable without a pointer */}
      <ul className="ms-sr-only">{shown.map((n) => <li key={n.uuid}><Link to={link(n)}>{n.name}</Link></li>)}</ul>
    </Stack>
  );
}
