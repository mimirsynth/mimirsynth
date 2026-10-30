import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, ConfirmDialog, DataTable, EmptyState, FilePicker, Modal, MutationError, Notice, Pill, SelectField, TextArea, TextField } from "../ui";

export type Item = { text: string; kind: "any" | "fact" | "chunk" | "doc" };
export type RefQuery = { id?: number; query: string; expect: Item[]; avoid: Item[]; docs: boolean | null; note: string };
type Found = Item & { found_in: string[] };
type Result = { id: number; query: string; error?: string; expected: number; found: number; false_positives: number; docs_ok: boolean | null; ms?: number; expect: Found[]; avoid: Found[] };
type Delta = { found: number; false_positives: number; docs_mismatch: number; expected: number; regressed: boolean };
type Summary = { queries: number; errors: number; expected: number; found: number; recall: number | null; false_positives: number; docs_mismatch: number;
  by_kind: Record<string, { found: number; false_positives: number }>; ms_p50: number | null; ms_max: number | null; previous_run: number | null; delta: Delta | null };
type Run = { id: number; status: string; reason: string; params: Record<string, number>; summary: Summary | null; error: string; created_at: string; finished_at: string | null; results?: Result[] };

const KIND: Record<string, string> = { any: T("cualquiera"), fact: T("hecho"), chunk: T("fragmento"), doc: T("documento") };
const DOCS = [{ value: "any", label: T("Da igual") }, { value: "yes", label: T("Debe haber pasajes de documentos") }, { value: "no", label: T("No debe haber pasajes de documentos") }];
const PARAM: Record<string, string> = { min_sim: T("umbral"), docs: T("pasajes"), facts: T("hechos"), chunks: T("fragmentos") };
const empty: RefQuery = { query: "", expect: [], avoid: [], docs: null, note: "" };

const lines = (items: Item[]) => items.map((i) => (i.kind === "any" ? i.text : `${i.kind}: ${i.text}`)).join("\n");
const parse = (s: string): Item[] => s.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
  const m = /^(fact|chunk|doc|any):\s*(.+)$/.exec(l);
  return m ? { kind: m[1] as Item["kind"], text: m[2].slice(0, 500) } : { kind: "any", text: l.slice(0, 500) };
});

/** Alta o edición de una consulta de referencia. También la usa Preguntar con lo marcado como «debe salir» y «sobra». */
export function RefQueryForm({ graph, initial, onClose }: { graph: string; initial: RefQuery | null; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [q, setQ] = useState(initial?.query ?? "");
  const [expect, setExpect] = useState(lines(initial?.expect ?? []));
  const [avoid, setAvoid] = useState(lines(initial?.avoid ?? []));
  const [docs, setDocs] = useState(initial?.docs === true ? "yes" : initial?.docs === false ? "no" : "any");
  const [note, setNote] = useState(initial?.note ?? "");
  const save = useMutation({
    mutationFn: () => {
      const body = { query: q, expect: parse(expect), avoid: parse(avoid), docs: docs === "any" ? null : docs === "yes", note };
      return initial?.id ? send("PATCH", `brains/${graph}/refqueries/${initial.id}`, { ...body, clear_docs: docs === "any" }) : send("POST", `brains/${graph}/refqueries`, body);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["refqueries", graph] }); onClose(); } });
  return (
    <Modal opened={initial !== null} onClose={onClose} title={initial?.id ? t("Editar consulta de referencia") : t("Nueva consulta de referencia")} size="lg">
      <Stack gap="xs">
        <TextArea label={t("Consulta")} autosize minRows={2} value={q} onChange={(e) => setQ(e.currentTarget.value)} data-autofocus />
        <TextArea label={t("Debe aparecer")} autosize minRows={2} maxRows={8} value={expect} onChange={(e) => setExpect(e.currentTarget.value)}
          description={t("Un texto por línea; cuenta como encontrado si aparece en algún resultado, sin contar mayúsculas ni espacios. Empieza la línea por «fact:», «chunk:» o «doc:» para exigir el tipo de resultado.")} />
        <TextArea label={t("No debe aparecer")} autosize minRows={2} maxRows={8} value={avoid} onChange={(e) => setAvoid(e.currentTarget.value)}
          description={t("Falsos positivos conocidos, con el mismo formato.")} />
        <SelectField label={t("Sección de documentos")} w={360} data={DOCS.map((d) => ({ ...d, label: t(d.label) }))} value={docs} onChange={(v) => v && setDocs(v)} allowDeselect={false} />
        <TextField label={t("Nota")} value={note} onChange={(e) => setNote(e.currentTarget.value)} />
        <MutationError error={save.error} />
        <Group justify="flex-end"><Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn><Btn kind="primary" icon="save" disabled={!q.trim()} loading={save.isPending} onClick={() => save.mutate()}>{t("Guardar")}</Btn></Group>
      </Stack>
    </Modal>
  );
}

function Params({ p }: { p: Record<string, number> }) {
  const { t } = useTranslation();
  const keys = Object.keys(p);
  return keys.length ? <Group gap={4}>{keys.map((k) => <Pill key={k} size="xs" tone="alt">{`${t(PARAM[k] ?? k)} ${p[k]}`}</Pill>)}</Group> : <Text size="xs" c="dimmed">{t("ajustes en vigor")}</Text>;
}

function DeltaPill({ d }: { d: Delta | null | undefined }) {
  const { t } = useTranslation();
  if (!d) return <Text size="xs" c="dimmed">—</Text>;
  const sign = (n: number) => (n > 0 ? `+${n}` : `${n}`);
  const better = d.found > 0 || d.false_positives < 0;
  return <Group gap={6} wrap="nowrap">
    <Pill size="xs" tone={d.regressed ? "danger" : better ? "success" : "neutral"}>{d.regressed ? t("empeora") : better ? t("mejora") : t("igual")}</Pill>
    <Text size="xs" c="dimmed">{t("encontrados {{f}} · falsos positivos {{fp}}", { f: sign(d.found), fp: sign(d.false_positives) })}</Text>
  </Group>;
}

/** Consultas de referencia del brain y sus ejecuciones: medir el recall antes y después de cambiar el umbral, el modelo o los pesos. */
export default function RefQueries({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["refqueries", graph], queryFn: () => get<{ items: RefQuery[]; last_run: Run | null }>(`brains/${graph}/refqueries`) });
  const runs = useQuery({ queryKey: ["refqueries", graph, "runs"], queryFn: () => get<{ items: Run[] }>(`brains/${graph}/refqueries/runs`),
    refetchInterval: (qr) => (qr.state.data?.items.some((r) => r.status === "queued" || r.status === "running") ? 2000 : false) });
  const [edit, setEdit] = useState<RefQuery | null>(null);
  const [del, setDel] = useState<RefQuery | null>(null);
  const [sweep, setSweep] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const detail = useQuery({ queryKey: ["refqueries", graph, "run", open], enabled: open !== null, queryFn: () => get<Run>(`brains/${graph}/refqueries/runs/${open}`) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["refqueries", graph] });
  const values = sweep.split(/[\s;]+/).map((x) => Number(x.replace(",", "."))).filter((x) => !Number.isNaN(x) && x > 0 && x <= 1);
  const run = useMutation({ mutationFn: (sw: number[]) => send("POST", `brains/${graph}/refqueries/runs`, { sweep: sw }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (q: RefQuery) => send("DELETE", `brains/${graph}/refqueries/${q.id}`), onSuccess: refresh });
  const imp = useMutation({ mutationFn: async (f: File) => { const data = JSON.parse(await f.text()); return send<{ added: number; skipped: number }>("POST", `brains/${graph}/refqueries/import`, { items: Array.isArray(data) ? data : data.items }); },
    onSuccess: refresh });
  const exportJson = async () => {
    const data = await get<{ items: RefQuery[] }>(`brains/${graph}/refqueries/export`);
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `consultas-de-referencia-${graph}.json`; link.click(); URL.revokeObjectURL(url);
  };
  const items = list.data?.items ?? [];
  const d = detail.data;
  return (
    <Stack gap="md">
      <Notice tone="info">{t("Preguntas con lo que su recall debe traer y lo que no. Al ejecutarlas se cuentan los esperados encontrados y los falsos positivos, para cambiar el umbral de los pasajes, el modelo de embeddings o los pesos con datos. «Simular» prueba otros umbrales sin tocar los ajustes. Tras un cambio de modelo de embeddings se ejecutan solas y, si empeoran, se avisa.")}</Notice>
      <Group gap="xs" align="flex-end">
        <Btn kind="primary" icon="play" disabled={!items.length} loading={run.isPending && !run.variables?.length} onClick={() => run.mutate([])}>{t("Ejecutar")}</Btn>
        <TextField label={t("Umbrales a simular")} placeholder="0,68 0,70 0,72" w={200} value={sweep} onChange={(e) => setSweep(e.currentTarget.value)} />
        <Btn icon="search" disabled={!items.length || !values.length} loading={run.isPending && !!run.variables?.length} onClick={() => run.mutate(values)}>{t("Simular")}</Btn>
        <Btn icon="plus" onClick={() => setEdit(empty)}>{t("Nueva consulta")}</Btn>
        <FilePicker label={t("Importar")} accept=".json,application/json" loading={imp.isPending} onFiles={(fl) => imp.mutate(fl[0])} />
        <Btn icon="download" disabled={!items.length} onClick={() => void exportJson()}>{t("Exportar")}</Btn>
      </Group>
      {imp.data && <Text size="xs" c="dimmed">{t("Importadas {{added}}; saltadas por repetidas {{skipped}}.", imp.data)}</Text>}
      <MutationError error={run.error ?? imp.error ?? remove.error} />

      <Stack gap="xs">
        <Text fw={600} size="sm">{t("Ejecuciones")}</Text>
        {runs.data?.items.length ? <DataTable fz="sm">
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Fecha")}</DataTable.Th><DataTable.Th>{t("Parámetros")}</DataTable.Th><DataTable.Th>{t("Encontrados")}</DataTable.Th>
            <DataTable.Th>{t("Falsos positivos")}</DataTable.Th><DataTable.Th>{t("Documentos al revés")}</DataTable.Th><DataTable.Th>{t("Mediana")}</DataTable.Th><DataTable.Th>{t("Frente a la anterior")}</DataTable.Th><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{runs.data.items.map((r) => (
            <DataTable.Tr key={r.id}>
              <DataTable.Td>{fmt(r.created_at)}{r.reason === "embedding.switched" && <Pill size="xs" tone="alt">{t("cambio de modelo")}</Pill>}</DataTable.Td>
              <DataTable.Td><Params p={r.params} /></DataTable.Td>
              {r.summary ? <>
                <DataTable.Td>{`${r.summary.found}/${r.summary.expected}`}{r.summary.recall !== null ? ` (${Math.round(r.summary.recall * 100)} %)` : ""}</DataTable.Td>
                <DataTable.Td>{r.summary.false_positives}</DataTable.Td>
                <DataTable.Td>{r.summary.docs_mismatch}</DataTable.Td>
                <DataTable.Td>{r.summary.ms_p50 !== null ? `${r.summary.ms_p50} ms` : "—"}</DataTable.Td>
                <DataTable.Td><DeltaPill d={r.summary.delta} /></DataTable.Td>
              </> : <DataTable.Td colSpan={5}><Pill size="xs" tone={r.status === "error" ? "danger" : "warn"} title={r.error || undefined}>{r.status === "error" ? t("error") : t("en curso")}</Pill></DataTable.Td>}
              <DataTable.Td>{r.summary && <Btn size="row" onClick={() => setOpen(r.id)}>{t("Ver")}</Btn>}</DataTable.Td>
            </DataTable.Tr>))}</DataTable.Tbody>
        </DataTable> : <EmptyState>{t("Aún no se ha ejecutado ninguna vez.")}</EmptyState>}
      </Stack>

      <Stack gap="xs">
        <Text fw={600} size="sm">{t("Consultas ({{n}})", { n: items.length })}</Text>
        {items.length ? <DataTable fz="sm">
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Consulta")}</DataTable.Th><DataTable.Th>{t("Debe aparecer")}</DataTable.Th><DataTable.Th>{t("No debe aparecer")}</DataTable.Th><DataTable.Th>{t("Documentos")}</DataTable.Th><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{items.map((q) => (
            <DataTable.Tr key={q.id}>
              <DataTable.Td><Text size="sm" lineClamp={2}>{q.query}</Text>{q.note && <Text size="xs" c="dimmed">{q.note}</Text>}</DataTable.Td>
              <DataTable.Td>{q.expect.length}</DataTable.Td>
              <DataTable.Td>{q.avoid.length}</DataTable.Td>
              <DataTable.Td>{q.docs === null ? t("da igual") : q.docs ? t("sí") : t("no")}</DataTable.Td>
              <DataTable.Td><Group gap={6} wrap="nowrap"><Btn size="row" icon="edit" onClick={() => setEdit(q)}>{t("Editar")}</Btn><Btn kind="danger" size="row" icon="trash" onClick={() => setDel(q)}>{t("Borrar")}</Btn></Group></DataTable.Td>
            </DataTable.Tr>))}</DataTable.Tbody>
        </DataTable> : <EmptyState>{t("No hay consultas de referencia. Créalas aquí, impórtalas desde un JSON o guárdalas desde Preguntar marcando lo que debe salir y lo que sobra.")}</EmptyState>}
      </Stack>

      {edit && <RefQueryForm key={edit.id ?? "new"} graph={graph} initial={edit} onClose={() => setEdit(null)} />}
      <ConfirmDialog opened={!!del} onClose={() => setDel(null)} title={t("Borrar consulta de referencia")} action={t("Borrar")} subject={del?.query}
        warning={t("Las ejecuciones anteriores conservan su resultado.")} onConfirm={() => remove.mutateAsync(del!)} />
      <Modal opened={open !== null} onClose={() => setOpen(null)} title={t("Ejecución #{{id}}", { id: open })} size="xl">
        {d?.summary && <Stack gap="sm">
          <Group gap="xs"><Params p={d.params} /><DeltaPill d={d.summary.delta} />
            <Text size="xs" c="dimmed">{t("por tipo: hechos {{f}}, fragmentos {{c}}, documentos {{d}} encontrados", { f: d.summary.by_kind.fact.found, c: d.summary.by_kind.chunk.found, d: d.summary.by_kind.doc.found })}</Text></Group>
          {d.summary.delta?.regressed && <Notice tone="warn">{t("Empeora respecto a la ejecución anterior con los ajustes en vigor.")}</Notice>}
          <DataTable fz="sm">
            <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Consulta")}</DataTable.Th><DataTable.Th>{t("Esperados")}</DataTable.Th><DataTable.Th>{t("Falsos positivos")}</DataTable.Th><DataTable.Th>{t("Documentos")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{(d.results ?? []).map((r) => (
              <DataTable.Tr key={r.id}>
                <DataTable.Td><Text size="sm">{r.query}</Text>{r.error && <Text size="xs" className="ms-text-danger">{r.error}</Text>}
                  {r.expect.filter((i) => !i.found_in.length).map((i, n) => <Text key={`e${n}`} size="xs" c="dimmed">{t("falta:")} {i.text} <Pill size="xs">{t(KIND[i.kind])}</Pill></Text>)}
                  {r.avoid.filter((i) => i.found_in.length).map((i, n) => <Text key={`a${n}`} size="xs" className="ms-text-danger">{t("sobra:")} {i.text} ({i.found_in.map((k) => t(KIND[k])).join(", ")})</Text>)}</DataTable.Td>
                <DataTable.Td>{`${r.found}/${r.expected}`}</DataTable.Td>
                <DataTable.Td>{r.false_positives ? <Pill size="xs" tone="danger">{r.false_positives}</Pill> : 0}</DataTable.Td>
                <DataTable.Td>{r.docs_ok === null ? "—" : r.docs_ok ? <Pill size="xs" tone="success">{t("bien")}</Pill> : <Pill size="xs" tone="danger">{t("al revés")}</Pill>}</DataTable.Td>
              </DataTable.Tr>))}</DataTable.Tbody>
          </DataTable>
        </Stack>}
      </Modal>
    </Stack>
  );
}
