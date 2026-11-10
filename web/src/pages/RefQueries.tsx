import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Block, Btn, CellText, ConfirmDialog, DataState, DataTable, DialogActions, EmptyState, FilePicker, Modal, MutationError, Notice, Pill, SelectField, TextArea, TextField, ViewBar } from "../ui";

export type Item = { text: string; kind: "any" | "fact" | "chunk" | "doc" };
export type RefQuery = { id?: number; query: string; expect: Item[]; avoid: Item[]; docs: boolean | null; note: string };
type Found = Item & { found_in: string[] };
type Result = { id: number; query: string; error?: string; expected: number; found: number; false_positives: number; docs_ok: boolean | null; ms?: number; expect: Found[]; avoid: Found[] };
type Delta = { found: number; false_positives: number; docs_mismatch: number; compared: number; regressed: boolean;
  lost: { id: number; text: string }[]; new_false_positives: { id: number; text: string }[] };
type Summary = { queries: number; errors: number; expected: number; found: number; recall: number | null; false_positives: number; docs_mismatch: number;
  by_kind: Record<string, { found: number; false_positives: number }>; ms_p50: number | null; ms_max: number | null; previous_run: number | null; delta: Delta | null };
type Run = { id: number; status: string; reason: string; params: Record<string, number>; summary: Summary | null; error: string; created_at: string; finished_at: string | null; results?: Result[] };

const KIND: Record<string, string> = { any: T("cualquiera"), fact: T("hecho"), chunk: T("fragmento"), doc: T("documento") };
const DOCS = [{ value: "any", label: T("Da igual") }, { value: "yes", label: T("Debe haber pasajes de documentos") }, { value: "no", label: T("No debe haber pasajes de documentos") }];
const PARAM: Record<string, string> = { min_sim: T("umbral"), min_similarity: T("umbral de hechos y fragmentos"), docs: T("pasajes"), facts: T("hechos"), chunks: T("fragmentos") };
const SWEEP_OF = [{ value: "min_sim", label: T("De los pasajes") }, { value: "min_similarity", label: T("De los hechos y fragmentos") }];
const REASON: Record<string, string> = { "embedding.before": T("antes del cambio de modelo"), "embedding.switched": T("tras el cambio de modelo") };
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
      <Stack gap="sm">
        <TextArea label={t("Consulta")} autosize minRows={2} value={q} onChange={(e) => setQ(e.currentTarget.value)} data-autofocus />
        <TextArea label={t("Debe aparecer")} autosize minRows={2} maxRows={8} value={expect} onChange={(e) => setExpect(e.currentTarget.value)}
          description={t("Un texto por línea; cuenta como encontrado si aparece en algún resultado, sin contar mayúsculas ni espacios. Empieza la línea por «fact:», «chunk:» o «doc:» para exigir el tipo de resultado.")} />
        <TextArea label={t("No debe aparecer")} autosize minRows={2} maxRows={8} value={avoid} onChange={(e) => setAvoid(e.currentTarget.value)}
          description={t("Falsos positivos conocidos, con el mismo formato.")} />
        <SelectField label={t("Sección de documentos")} data={DOCS.map((d) => ({ ...d, label: t(d.label) }))} value={docs} onChange={(v) => v && setDocs(v)} allowDeselect={false} />
        <TextField label={t("Nota")} value={note} onChange={(e) => setNote(e.currentTarget.value)} />
        <MutationError error={save.error} />
        <DialogActions><Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn><Btn kind="primary" icon="save" disabled={!q.trim()} loading={save.isPending} onClick={() => save.mutate()}>{t("Guardar")}</Btn></DialogActions>
      </Stack>
    </Modal>
  );
}

function Params({ p }: { p: Record<string, number> }) {
  const { t } = useTranslation();
  const keys = Object.keys(p);
  return keys.length ? <Group gap={4}>{keys.map((k) => <Pill key={k} tone="alt">{`${t(PARAM[k] ?? k)} ${p[k]}`}</Pill>)}</Group> : <>{t("ajustes en vigor")}</>;
}

function DeltaPill({ d }: { d: Delta | null | undefined }) {
  const { t } = useTranslation();
  if (!d) return <>—</>;
  const sign = (n: number) => (n > 0 ? `+${n}` : `${n}`);
  const better = d.found > 0 || d.false_positives < 0;
  return <CellText sub={<span title={t("Solo cuenta lo que está en las dos ejecuciones: las mismas consultas y los mismos textos.")}>
      {t("encontrados {{f}} · falsos positivos {{fp}} · {{n}} consultas comparadas", { f: sign(d.found), fp: sign(d.false_positives), n: d.compared })}</span>}>
    <Pill tone={d.regressed ? "danger" : better ? "success" : "neutral"}>{d.regressed ? t("empeora") : better ? t("mejora") : t("igual")}</Pill>
  </CellText>;
}

/** Consultas de referencia del brain y sus ejecuciones: medir el recall antes y después de cambiar el umbral, el modelo o los pesos.
 *  The view: a bar with what they are for behind its «i», the thresholds to simulate and the actions; the queries as the table; the runs
 *  as a block below, each opening its detail in a dialog. */
export default function RefQueries({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["refqueries", graph], queryFn: () => get<{ items: RefQuery[]; last_run: Run | null }>(`brains/${graph}/refqueries`) });
  const runs = useQuery({ queryKey: ["refqueries", graph, "runs"], queryFn: () => get<{ items: Run[] }>(`brains/${graph}/refqueries/runs`),
    refetchInterval: (qr) => (qr.state.data?.items.some((r) => r.status === "queued" || r.status === "running") ? 2000 : false) });
  const [edit, setEdit] = useState<RefQuery | null>(null);
  const [del, setDel] = useState<RefQuery | null>(null);
  const [sweep, setSweep] = useState("");
  const [sweepOf, setSweepOf] = useState("min_sim");
  const [open, setOpen] = useState<number | null>(null);
  const detail = useQuery({ queryKey: ["refqueries", graph, "run", open], enabled: open !== null, queryFn: () => get<Run>(`brains/${graph}/refqueries/runs/${open}`) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["refqueries", graph] });
  const values = sweep.split(/[\s;]+/).map((x) => Number(x.replace(",", "."))).filter((x) => !Number.isNaN(x) && x > 0 && x <= 1);
  const run = useMutation({ mutationFn: (sw: number[]) => send("POST", `brains/${graph}/refqueries/runs`, { sweep: sw, sweep_of: sweepOf }), onSuccess: refresh });
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
    <>
      <ViewBar title={t("Consultas de referencia")}
        help={t("Preguntas con lo que su recall debe traer y lo que no. Al ejecutarlas se cuentan los esperados encontrados y los falsos positivos, para cambiar el umbral de los pasajes, el modelo de embeddings o los pesos con datos. «Simular» prueba otros umbrales sin tocar los ajustes. Tras un cambio de modelo de embeddings se ejecutan solas y, si empeoran, se avisa.")}
        meta={<>{t("Consultas ({{n}})", { n: items.length })}{imp.data && <> · {t("Importadas {{added}}; saltadas por repetidas {{skipped}}.", imp.data)}</>}</>}
        actions={<>
          <Btn icon="search" disabled={!items.length || !values.length} loading={run.isPending && !!run.variables?.length} onClick={() => run.mutate(values)}>{t("Simular")}</Btn>
          <Btn icon="plus" onClick={() => setEdit(empty)}>{t("Nueva consulta")}</Btn>
          <FilePicker label={t("Importar")} accept=".json,application/json" loading={imp.isPending} onFiles={(fl) => imp.mutate(fl[0])} />
          <Btn icon="download" disabled={!items.length} onClick={() => void exportJson()}>{t("Exportar")}</Btn>
          <Btn kind="primary" icon="play" disabled={!items.length} loading={run.isPending && !run.variables?.length} onClick={() => run.mutate([])}>{t("Ejecutar")}</Btn>
        </>}>
        <TextField label={t("Umbrales a simular")} placeholder="0,68 0,70 0,72" value={sweep} onChange={(e) => setSweep(e.currentTarget.value)} />
        <SelectField label={t("Umbral")} data={SWEEP_OF.map((d) => ({ ...d, label: t(d.label) }))} value={sweepOf} onChange={(v) => v && setSweepOf(v)} allowDeselect={false} />
      </ViewBar>
      <MutationError error={run.error ?? imp.error ?? remove.error} />

      {!list.data ? <DataState query={list} /> : items.length ? <DataTable fz="sm" aria-label={t("Consultas")}>
        <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Consulta")}</DataTable.Th><DataTable.Th>{t("Debe aparecer")}</DataTable.Th><DataTable.Th>{t("No debe aparecer")}</DataTable.Th><DataTable.Th>{t("Documentos")}</DataTable.Th><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{items.map((q) => (
          <DataTable.Tr key={q.id}>
            <DataTable.Td><CellText sub={q.note || undefined}><Text size="sm" lineClamp={2}>{q.query}</Text></CellText></DataTable.Td>
            <DataTable.Td className="ms-data">{q.expect.length}</DataTable.Td>
            <DataTable.Td className="ms-data">{q.avoid.length}</DataTable.Td>
            <DataTable.Td>{q.docs === null ? t("da igual") : q.docs ? t("sí") : t("no")}</DataTable.Td>
            <DataTable.Td><Group gap={6} wrap="nowrap"><Btn size="row" icon="edit" onClick={() => setEdit(q)}>{t("Editar")}</Btn><Btn kind="danger" size="row" icon="trash" onClick={() => setDel(q)}>{t("Borrar")}</Btn></Group></DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable> : <EmptyState>{t("No hay consultas de referencia. Créalas aquí, impórtalas desde un JSON o guárdalas desde Preguntar marcando lo que debe salir y lo que sobra.")}</EmptyState>}

      <Block title={t("Ejecuciones")} count={runs.data?.items.length}>
        {!runs.data ? <DataState query={runs} /> : runs.data.items.length ? <DataTable fz="sm" aria-label={t("Ejecuciones")}>
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Fecha")}</DataTable.Th><DataTable.Th>{t("Parámetros")}</DataTable.Th><DataTable.Th>{t("Encontrados")}</DataTable.Th>
            <DataTable.Th>{t("Falsos positivos")}</DataTable.Th><DataTable.Th>{t("Documentos al revés")}</DataTable.Th><DataTable.Th>{t("Mediana")}</DataTable.Th><DataTable.Th>{t("Frente a la anterior")}</DataTable.Th><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{runs.data.items.map((r) => (
            <DataTable.Tr key={r.id}>
              <DataTable.Td><CellText sub={REASON[r.reason] ? <Pill tone="alt">{t(REASON[r.reason])}</Pill> : undefined}><span className="ms-data">{fmt(r.created_at)}</span></CellText></DataTable.Td>
              <DataTable.Td><Params p={r.params} /></DataTable.Td>
              {r.summary ? <>
                <DataTable.Td className="ms-data">{`${r.summary.found}/${r.summary.expected}`}{r.summary.recall !== null ? ` (${Math.round(r.summary.recall * 100)} %)` : ""}</DataTable.Td>
                <DataTable.Td className="ms-data">{r.summary.false_positives}</DataTable.Td>
                <DataTable.Td className="ms-data">{r.summary.docs_mismatch}</DataTable.Td>
                <DataTable.Td className="ms-data">{r.summary.ms_p50 !== null ? `${r.summary.ms_p50} ms` : "—"}</DataTable.Td>  {/* i18n-ok: unit */}
                <DataTable.Td><DeltaPill d={r.summary.delta} /></DataTable.Td>
              </> : <DataTable.Td colSpan={5}><Pill tone={r.status === "error" ? "danger" : "warn"} title={r.error || undefined}>{r.status === "error" ? t("error") : t("en curso")}</Pill></DataTable.Td>}
              <DataTable.Td>{r.summary && <Btn size="row" onClick={() => setOpen(r.id)}>{t("Ver")}</Btn>}</DataTable.Td>
            </DataTable.Tr>))}</DataTable.Tbody>
        </DataTable> : <EmptyState>{t("Aún no se ha ejecutado ninguna vez.")}</EmptyState>}
      </Block>

      {edit && <RefQueryForm key={edit.id ?? "new"} graph={graph} initial={edit} onClose={() => setEdit(null)} />}
      <ConfirmDialog opened={!!del} onClose={() => setDel(null)} title={t("Borrar consulta de referencia")} action={t("Borrar")} subject={del?.query}
        warning={t("Las ejecuciones anteriores conservan su resultado.")} onConfirm={() => remove.mutateAsync(del!)} />
      <Modal opened={open !== null} onClose={() => setOpen(null)} title={t("Ejecución #{{id}}", { id: open })} size="xl">
        {!d ? <DataState query={detail} /> : d.summary && <Stack gap="sm">
          {/* the run's parameters and how it compares with the one before, then what it found by kind */}
          <ViewBar title={t("Ejecución #{{id}}", { id: open })}
            meta={t("por tipo: hechos {{f}}, fragmentos {{c}}, documentos {{d}} encontrados", { f: d.summary.by_kind.fact.found, c: d.summary.by_kind.chunk.found, d: d.summary.by_kind.doc.found })}>
            <Params p={d.params} /><DeltaPill d={d.summary.delta} />
          </ViewBar>
          {d.summary.delta?.regressed && <Notice tone="warn" title={t("Empeora respecto a la ejecución anterior con los ajustes en vigor.")}>
            {d.summary.delta.lost.map((x, n) => <div key={`l${n}`}>{t("Deja de salir:")} {x.text}</div>)}
            {d.summary.delta.new_false_positives.map((x, n) => <div key={`f${n}`}>{t("Falso positivo nuevo:")} {x.text}</div>)}
          </Notice>}
          <DataTable fz="sm" aria-label={t("Ejecución #{{id}}", { id: open })}>
            <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Consulta")}</DataTable.Th><DataTable.Th>{t("Esperados")}</DataTable.Th><DataTable.Th>{t("Falsos positivos")}</DataTable.Th><DataTable.Th>{t("Documentos")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{(d.results ?? []).map((r) => {
              const missing = r.expect.filter((i) => !i.found_in.length), extra = r.avoid.filter((i) => i.found_in.length);
              return (
                <DataTable.Tr key={r.id}>
                  {/* under the query, its error and what it missed or brought too much */}
                  <DataTable.Td><CellText sub={(r.error || missing.length || extra.length) ? <>
                    {r.error && <div className="ms-text-danger">{r.error}</div>}
                    {missing.map((i, n) => <div key={`e${n}`}>{t("falta:")} {i.text} <Pill>{t(KIND[i.kind])}</Pill></div>)}
                    {extra.map((i, n) => <div key={`a${n}`} className="ms-text-danger">{t("sobra:")} {i.text} ({i.found_in.map((k) => t(KIND[k])).join(", ")})</div>)}
                  </> : undefined}>{r.query}</CellText></DataTable.Td>
                  <DataTable.Td className="ms-data">{`${r.found}/${r.expected}`}</DataTable.Td>
                  <DataTable.Td>{r.false_positives ? <Pill tone="danger">{r.false_positives}</Pill> : 0}</DataTable.Td>
                  <DataTable.Td>{r.docs_ok === null ? "—" : r.docs_ok ? <Pill tone="success">{t("bien")}</Pill> : <Pill tone="danger">{t("al revés")}</Pill>}</DataTable.Td>
                </DataTable.Tr>);
            })}</DataTable.Tbody>
          </DataTable>
        </Stack>}
      </Modal>
    </>
  );
}
