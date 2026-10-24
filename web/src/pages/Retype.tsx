import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, Check, ClearFilters, ColHead, DataTable, FillArea, Notice, NumberField, Page, Pill, ProgressBar, Segments, SliderField, useTableView, MutationError } from "../ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, send } from "../api";

type Item = { id: number; name: string; current_type: string; suggested_type: string; confidence: number | null; status: string; previous_type: string; reason?: string };
type Ov = { hidden_below_threshold: number; ontology: boolean; decider: boolean; counts: Record<string, number>; progress: { running: boolean; done: number; total: number; error: string | null }; items: Item[] };

const RT_COLS = { name: { get: (i: Item) => i.name }, cur: { get: (i: Item) => i.current_type || "sin tipo", exact: true }, sug: { get: (i: Item) => i.suggested_type, exact: true }, conf: { get: (i: Item) => i.confidence ?? -1 }, reason: { get: (i: Item) => i.reason ?? "" } };

export default function Retype({ graph, role }: { graph: string; role: string }) {
  const qc = useQueryClient();
  const isAdmin = ["admin", "owner"].includes(role);
  const [status, setStatus] = useState("pending");
  const [minConf, setMinConf] = useState(0.8);
  const [sel, setSel] = useState<number[]>([]);
  const [limit, setLimit] = useState<number | string>(100);
  const base = `brains/${graph}/retype`;
  const q = useQuery({ queryKey: ["retype", graph, status, minConf], enabled: isAdmin, refetchInterval: (c) => (c.state.data?.progress.running ? 3000 : false),
    queryFn: () => get<Ov>(base, { status, min_conf: status === "pending" ? minConf : 0 }) });
  const refresh = () => { setSel([]); qc.invalidateQueries({ queryKey: ["retype", graph] }); };
  const scan = useMutation({ mutationFn: () => send("POST", `${base}/scan`, { limit: Number(limit) }), onSuccess: refresh });
  const apply = useMutation({ mutationFn: (ids: number[]) => send<{ applied: number }>("POST", `${base}/apply`, { ids }), onSuccess: refresh });
  const reject = useMutation({ mutationFn: (ids: number[]) => send("POST", `${base}/reject`, { ids }), onSuccess: refresh });
  const revert = useMutation({ mutationFn: (id: number) => send("POST", `${base}/${id}/revert`), onSuccess: refresh });
  const v = useTableView(q.data?.items ?? [], RT_COLS, { key: "conf", dir: "desc" });
  if (!isAdmin) return <Text c="dimmed" size="sm">Solo los administradores del brain pueden corregir tipos.</Text>;
  const d = q.data; const items = v.rows; const p = d?.progress;
  const allIds = items.map((i) => i.id);
  return (
    <Page>
      <Text size="sm" c="dimmed" maw={760}>Graphiti no cambia el tipo de las entidades ya existentes, así que las clasificadas con tipos genéricos (Object, Organization, Location…) se quedan así. El decisor revisa cada una con la ontología del brain como opciones y propone un tipo; tú apruebas, y el cambio es reversible.</Text>
      {d && !d.ontology && <Notice tone="warn">Este brain no tiene ontología. Aplica un paquete en la pestaña Ontología.</Notice>}
      {d && !d.decider && <Notice tone="warn">No hay decisor configurado (Administración → Proveedores IA → Decisores).</Notice>}
      <Group align="flex-end" gap="xs">
        <NumberField size="xs" label="Entidades a analizar" min={1} max={1000} value={limit} onChange={setLimit} w={150} />
        <Btn kind="primary" disabled={!d?.ontology || !d?.decider || p?.running} loading={scan.isPending} onClick={() => scan.mutate()} icon="search">Analizar</Btn>

      </Group>
      <MutationError error={scan.error} />
      {p?.running && <ProgressBar done={p.done} total={p.total} text={`Analizando… ${p.done} de ${p.total}`} />}
      {p?.error && !p.running && <Notice tone="warn">Último error del análisis: {p.error}</Notice>}
      <Segments label="Estado" value={status} onChange={(v) => { setStatus(v); setSel([]); }}
        data={[["pending", "Propuestos"], ["doubtful", "Dudosas"], ["none", "Sin tipo adecuado"], ["applied", "Aplicados"], ["rejected", "Rechazados"], ["same", "Ya correctos"]].map(([value, label]) => ({ value, label, count: d?.counts[value] ?? 0 }))} />
      {status === "pending" && <Group gap="md" align="center">
        <SliderField label="Confianza mínima" min={0.5} max={0.99} step={0.01} value={minConf} onChange={setMinConf} />
        {!!d?.hidden_below_threshold && <Text size="xs" c="dimmed">{d.hidden_below_threshold} más por debajo de ese umbral <Btn kind="link" onClick={() => setMinConf(0.5)}>Ver todas</Btn></Text>}
      </Group>}
      {status === "none" && <Text size="xs" c="dimmed" maw={760}>El decisor no encuentra ningún tipo de la ontología que encaje con estas entidades. No hace falta tocarlas; si hay muchas de una misma clase, es señal de que falta un tipo en la ontología.</Text>}
      {status === "doubtful" && <Text size="xs" c="dimmed" maw={760}>Nombres que no parecen una entidad concreta (rutas, opciones, frases, versiones, descripciones de un problema). No tiene sentido darles un tipo; si quieres, descártalas de esta lista.</Text>}
      {(status === "pending" || status === "doubtful") && <Group gap="xs">
        {status === "pending" && <>
        <Btn kind="primary" disabled={!sel.length} loading={apply.isPending} onClick={() => apply.mutate(sel)} icon="check">Aplicar seleccionadas ({sel.length})</Btn>
        <Btn size="row" disabled={!allIds.length} loading={apply.isPending} onClick={() => apply.mutate(allIds)} icon="check">Aplicar todas las visibles ({allIds.length})</Btn>
        </>}
        <Btn kind="danger" size="row" disabled={!sel.length} onClick={() => reject.mutate(sel)}>{status === "doubtful" ? "Descartar seleccionadas" : "Rechazar seleccionadas"}</Btn></Group>}
      <MutationError error={apply.error} />
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <FillArea><DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>{(status === "pending" || status === "doubtful") && <DataTable.Th w={30}><Check size="xs" aria-label="Seleccionar todo" checked={!!allIds.length && sel.length === allIds.length} onChange={(e) => setSel(e.currentTarget.checked ? allIds : [])} /></DataTable.Th>}
          <ColHead sort={v.sortProps("name")} filter={v.text("name")}>Entidad</ColHead>
          <ColHead sort={v.sortProps("cur")} filter={v.select("cur")}>Tipo actual</ColHead>
          {status === "doubtful" || status === "none" ? <ColHead filter={v.text("reason", "Motivo…")}>Motivo</ColHead> : <><ColHead sort={v.sortProps("sug")} filter={v.select("sug")}>Tipo propuesto</ColHead><ColHead sort={v.sortProps("conf")}>Confianza</ColHead></>}
          {status === "applied" && <DataTable.Th />}</DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>
          {items.map((i) => (
            <DataTable.Tr key={i.id}>
              {(status === "pending" || status === "doubtful") && <DataTable.Td><Check size="xs" aria-label={`Seleccionar ${i.name}`} checked={sel.includes(i.id)} onChange={(e) => setSel(e.currentTarget.checked ? [...sel, i.id] : sel.filter((x) => x !== i.id))} /></DataTable.Td>}
              <DataTable.Td>{i.name}</DataTable.Td><DataTable.Td><Pill>{i.current_type || "sin tipo"}</Pill></DataTable.Td>
              {status === "doubtful" || status === "none" ? <DataTable.Td><Text size="xs" c="dimmed">{i.reason || "—"}</Text></DataTable.Td> : <><DataTable.Td><Pill tone="success">{i.suggested_type}</Pill></DataTable.Td><DataTable.Td className="ms-data">{i.confidence ?? "—"}</DataTable.Td></>}
              {status === "applied" && <DataTable.Td><Btn size="row" loading={revert.isPending && revert.variables === i.id} onClick={() => revert.mutate(i.id)} icon="undo">Deshacer</Btn></DataTable.Td>}
            </DataTable.Tr>))}
          {items.length === 0 && <DataTable.Tr><DataTable.Td colSpan={6}><Text c="dimmed" size="sm">{status === "pending" ? "Nada propuesto por encima de esa confianza. Baja el umbral o lanza un análisis." : "Sin elementos."}</Text></DataTable.Td></DataTable.Tr>}
        </DataTable.Tbody>
      </DataTable></FillArea>
    </Page>
  );
}
