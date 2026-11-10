import { useTranslation } from "react-i18next";
import { Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Block, Btn, CellText, DataState, DataTable, DialogActions, EmptyState, Modal, MutationError, NumberField, Pill, SelectField, TextArea } from "../ui";
import { T } from "../i18n";

type Summary = { questions: number; errors: number; changed: number; gained: number; lost: number; empty_after: number | null; empty_before: number | null; outdated_after: number | null };
type Run = { id: number; status: string; params: Record<string, number | boolean>; size: number; summary: Summary | null; error: string; created_at: string; finished_at: string | null };
type Result = { sample_id: number; query: string; gained?: { kind: string; id: string }[]; lost?: { kind: string; id: string }[]; reordered?: boolean;
  empty_before?: boolean; empty_after?: boolean; changed?: boolean; outdated?: number; error?: string };

const ONOFF = [{ value: "", label: T("Como ahora") }, { value: "on", label: T("Activado") }, { value: "off", label: T("Desactivado") }];
const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)} %`);

/** Turn one real question into a reference query, once the person says what it must bring. */
function Promote({ graph, r, onClose }: { graph: string; r: Result; onClose: () => void }) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const go = useMutation({ mutationFn: () => send("POST", `brains/${graph}/replay/samples/${r.sample_id}/promote`, { expect: text.split("\n").map((x) => x.trim()).filter(Boolean) }), onSuccess: onClose });
  return (
    <Modal opened onClose={onClose} title={t("Convertir en consulta de referencia")}>
      <Stack gap="sm">
        <Text size="sm">«{r.query}»</Text>
        <TextArea label={t("Lo que debe traer")} description={t("Un texto por línea; cuenta como encontrado si aparece en algún resultado.")} autosize minRows={3}
          value={text} onChange={(e) => setText(e.currentTarget.value)} />
        <MutationError error={go.error} />
        <DialogActions>
          <Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn>
          <Btn kind="primary" loading={go.isPending} disabled={!text.trim()} onClick={() => go.mutate()}>{t("Crear la consulta")}</Btn>
        </DialogActions>
      </Stack>
    </Modal>
  );
}

/** Ask → Quality (issue 291): replay the brain's sample of real recalls with a candidate configuration and read what would change.
 *  A block with the replays as a table; «Repetir» opens the candidate configuration in a dialog, and a finished replay's detail opens as
 *  a block below, with each changed query ready to become a reference query. */
export default function ReplayRuns({ graph, samples }: { graph: string; samples: number }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const runs = useQuery({ queryKey: ["replay-runs", graph], queryFn: () => get<{ items: Run[] }>(`brains/${graph}/replay/runs`),
    refetchInterval: (q) => (q.state.data?.items.some((r) => r.status === "queued" || r.status === "running") ? 3000 : false) });
  const [min, setMin] = useState<number | string>("");
  const [trust, setTrust] = useState("");
  const [decay, setDecay] = useState("");
  const [card, setCard] = useState("");
  const [size, setSize] = useState<number | string>(100);
  const [form, setForm] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const [promote, setPromote] = useState<Result | null>(null);
  const flag = (v: string) => (v === "" ? undefined : v === "on");
  const start = useMutation({ mutationFn: () => send("POST", `brains/${graph}/replay/runs`, { sample: Number(size) || 100,
    candidate: { min_similarity: min === "" ? undefined : Number(min), trust: flag(trust), decay: flag(decay), state_card: flag(card) } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["replay-runs", graph] }) });
  const detail = useQuery({ queryKey: ["replay-run", graph, open], enabled: open !== null, queryFn: () => get<Run & { results: Result[] }>(`brains/${graph}/replay/runs/${open}`) });
  const describe = (p: Run["params"]) => Object.entries(p).map(([k, v]) => `${k}: ${typeof v === "boolean" ? (v ? t("sí") : t("no")) : v}`).join(" · ") || t("los ajustes de ahora");
  const items = runs.data?.items ?? [];
  const changed = detail.data?.results.filter((x) => x.changed || x.error) ?? [];
  const onoff = ONOFF.map((o) => ({ ...o, label: t(o.label) }));
  return (
    <>
      <Block title={t("Repetir la muestra con otra configuración")} count={samples && runs.data ? items.length : undefined}
        help={t("Vuelve a hacer las consultas reales guardadas con lo que elijas, sin cambiar nada para quien consulta, y dice qué cambiaría. Cada consulta es un embedding; como mucho 10 repeticiones por hora.")}
        actions={samples ? <Btn kind="primary" icon="refresh" onClick={() => { start.reset(); setForm(true); }}>{t("Repetir")}</Btn> : undefined}>
        {!samples ? <EmptyState>{t("Todavía no hay consultas guardadas en la muestra.")}</EmptyState>
          : !runs.data ? <DataState query={runs} />
          : items.length ? <DataTable fz="sm" aria-label={t("Repetir la muestra con otra configuración")}>
            <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Parámetros")}</DataTable.Th><DataTable.Th>{t("Fecha")}</DataTable.Th><DataTable.Th>{t("Resultado")}</DataTable.Th><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{items.map((r) => (
              <DataTable.Tr key={r.id}>
                <DataTable.Td>{describe(r.params)}</DataTable.Td>
                <DataTable.Td className="ms-data">{fmt(r.created_at)}</DataTable.Td>
                <DataTable.Td><CellText sub={r.error || undefined}>
                  {r.status !== "done" && <Pill tone={r.status === "error" ? "danger" : "neutral"}>{r.status === "error" ? t("con error") : t("en marcha")}</Pill>}
                  {r.summary && t("{{c}} de {{n}} consultas cambiarían · ganarían {{g}} elementos y perderían {{l}} · vacías: {{eb}} → {{ea}} · con algo desactualizado: {{o}}",
                    { c: r.summary.changed, n: r.summary.questions, g: r.summary.gained, l: r.summary.lost, eb: pct(r.summary.empty_before), ea: pct(r.summary.empty_after), o: pct(r.summary.outdated_after) })}
                </CellText></DataTable.Td>
                <DataTable.Td>{r.status === "done" && <Btn size="row" aria-pressed={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>{open === r.id ? t("Ocultar") : t("Ver el detalle")}</Btn>}</DataTable.Td>
              </DataTable.Tr>))}</DataTable.Tbody>
          </DataTable> : <EmptyState>{t("Aún no se ha ejecutado ninguna vez.")}</EmptyState>}
      </Block>
      {open !== null && <Block title={t("Detalle")} count={detail.data ? changed.length : undefined}
        actions={<Btn kind="ghost" size="row" icon="close" onClick={() => setOpen(null)}>{t("Cerrar")}</Btn>}>
        {!detail.data ? <DataState query={detail} /> : changed.length ? <DataTable fz="sm" aria-label={t("Detalle")}>
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Consulta")}</DataTable.Th><DataTable.Th>{t("Cambio")}</DataTable.Th><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{changed.map((x) => (
            <DataTable.Tr key={x.sample_id}>
              <DataTable.Td>«{x.query}»</DataTable.Td>
              <DataTable.Td>{x.error ? t("falló: {{e}}", { e: x.error }) : t("gana {{g}}, pierde {{l}}{{o}}{{e}}", { g: x.gained?.length ?? 0, l: x.lost?.length ?? 0,
                o: x.reordered ? `, ${t("cambia el orden")}` : "", e: x.empty_after ? `, ${t("vuelve vacía")}` : "" })}</DataTable.Td>
              <DataTable.Td><Btn size="row" onClick={() => setPromote(x)}>{t("Consulta de referencia")}</Btn></DataTable.Td>
            </DataTable.Tr>))}</DataTable.Tbody>
        </DataTable> : <EmptyState>{t("Ninguna consulta cambiaría.")}</EmptyState>}
      </Block>}
      <Modal opened={form} onClose={() => setForm(false)} title={t("Repetir la muestra con otra configuración")}>
        <Stack gap="sm">
          <NumberField label={t("Similitud mínima de un hecho")} min={0} max={1} step={0.01} decimalScale={2} placeholder={t("como ahora")} value={min} onChange={setMin} />
          <SelectField label={t("Peso por origen")} data={onoff} value={trust} onChange={(v) => setTrust(v ?? "")} allowDeselect={false} />
          <SelectField label={t("Envejecer por relación")} data={onoff} value={decay} onChange={(v) => setDecay(v ?? "")} allowDeselect={false} />
          <SelectField label={t("Estado actual primero")} data={onoff} value={card} onChange={(v) => setCard(v ?? "")} allowDeselect={false} />
          <NumberField label={t("Consultas")} min={1} max={500} value={size} onChange={setSize} />
          <MutationError error={start.error} />
          <DialogActions>
            <Btn kind="ghost" onClick={() => setForm(false)}>{t("Cancelar")}</Btn>
            <Btn kind="primary" icon="refresh" loading={start.isPending} onClick={() => start.mutate(undefined, { onSuccess: () => setForm(false) })}>{t("Repetir")}</Btn>
          </DialogActions>
        </Stack>
      </Modal>
      {promote && <Promote graph={graph} r={promote} onClose={() => setPromote(null)} />}
    </>
  );
}
