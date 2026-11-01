import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Brain, get, send } from "../api";
import { Btn, Check, DataTable, EmptyState, Modal, MutationError, Notice, NumberField, Pill, ProgressBar, Segments } from "../ui";

type Row = { kind: string; model: string; purpose: string; calls: number; errors_429: number; errors_5xx: number; errors_other: number;
  prompt_tokens: number; completion_tokens: number; estimated_calls: number; peak_rpm: number; cost: number; priced: boolean };
type Budget = { limit: number | null; unit: "tokens" | "cost"; pause: boolean; used: number; pct: number | null; paused: boolean; unpriced: string[] };
type BrainUsage = { days: number; rows: Row[]; budget: Budget };
type Engine = Row & { rpm_now: number; price: [number, number] | null };
type InstanceUsage = { days: number; engines: Engine[]; brains: { brain_id: number; slug: string; name: string; calls: number; tokens: number; errors_429: number; errors_5xx: number; cost: number; priced: boolean }[] };

export const PURPOSE: Record<string, string> = {
  extraction: T("Extracción de hechos"), decider: T("Decisor"), recall: T("Recall"), documents: T("Índice de documentos"), index: T("Índice de episodios"),
  facts: T("Edición de hechos"), retype: T("Corrector de tipos"), reindex: T("Cambio de modelo"), import: T("Importación"), other: T("Otros"),
};
const KIND: Record<string, string> = { llm: T("LLM"), embedding: T("Embeddings"), decision: T("Decisor") };
const num = (n: number) => n.toLocaleString();
const money = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 4 });

function Errors({ r }: { r: { errors_429: number; errors_5xx: number } }) {
  const { t } = useTranslation();
  return r.errors_429 || r.errors_5xx ? <Group gap={4}>
    {r.errors_429 > 0 && <Pill tone="warn" size="xs">{t("429: {{n}}", { n: r.errors_429 })}</Pill>}
    {r.errors_5xx > 0 && <Pill tone="danger" size="xs">{t("5xx: {{n}}", { n: r.errors_5xx })}</Pill>}
  </Group> : <Text size="xs" c="dimmed">—</Text>;
}

/** Consumo de IA de un brain en los últimos 30 días, por uso y motor, y su presupuesto mensual. */
export function BrainAiUsage({ brain }: { brain: Brain }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["ai-usage", brain.slug];
  const q = useQuery({ queryKey: key, queryFn: () => get<BrainUsage>(`brains/${brain.slug}/ai-usage`, { days: 30 }) });
  const [limit, setLimit] = useState<number | string>(""); const [unit, setUnit] = useState<"tokens" | "cost">("tokens"); const [pause, setPause] = useState(false);
  useEffect(() => { const b = q.data?.budget; if (b) { setLimit(b.limit ?? ""); setUnit(b.unit); setPause(b.pause); } }, [q.data]);
  const save = useMutation({ mutationFn: () => send<Budget>("PUT", `brains/${brain.slug}/ai-budget`, { limit: limit === "" ? null : Number(limit), unit, pause }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }) });
  const b = q.data?.budget;
  const rows = q.data?.rows ?? [];
  return (
    <Stack gap="sm">
      {b?.limit ? <Stack gap={4}>
        <ProgressBar done={Math.min(b.used, b.limit)} total={b.limit} text={t("Este mes: {{used}} de {{limit}} ({{pct}} %)", {
          used: b.unit === "cost" ? money(b.used) : num(b.used), limit: b.unit === "cost" ? money(b.limit) : num(b.limit), pct: b.pct ?? 0 })} />
        {b.paused && <Notice tone="warn">{t("Presupuesto agotado: la ingesta de propuestas está en pausa. Las aprobadas esperan y siguen solas al subir el presupuesto o al cambiar de mes.")}</Notice>}
        {b.unpriced.length > 0 && <Text size="xs" c="dimmed">{t("Sin precio, no cuentan en el coste: {{m}}", { m: b.unpriced.join(", ") })}</Text>}
      </Stack> : null}
      {rows.length ? <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <DataTable.Th>{t("Uso")}</DataTable.Th><DataTable.Th>{t("Motor")}</DataTable.Th><DataTable.Th>{t("Llamadas")}</DataTable.Th>
          <DataTable.Th>{t("Tokens (entrada / salida)")}</DataTable.Th><DataTable.Th>{t("Coste estimado")}</DataTable.Th>
          <DataTable.Th>{t("Pico por minuto")}</DataTable.Th><DataTable.Th>{t("Errores")}</DataTable.Th>
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{rows.map((r) => (
          <DataTable.Tr key={`${r.kind}:${r.model}:${r.purpose}`}>
            <DataTable.Td>{t(PURPOSE[r.purpose] ?? r.purpose)}</DataTable.Td>
            <DataTable.Td><Text size="xs">{t(KIND[r.kind] ?? r.kind)}</Text><Text size="xs" c="dimmed" className="ms-data">{r.model}</Text></DataTable.Td>
            <DataTable.Td>{num(r.calls)}</DataTable.Td>
            <DataTable.Td>{num(r.prompt_tokens)} / {num(r.completion_tokens)}{r.estimated_calls > 0 && <Text size="xs" c="dimmed">{t("{{n}} estimadas", { n: r.estimated_calls })}</Text>}</DataTable.Td>
            <DataTable.Td>{r.priced ? money(r.cost) : <Text size="xs" c="dimmed">{t("sin precio")}</Text>}</DataTable.Td>
            <DataTable.Td>{r.peak_rpm}</DataTable.Td>
            <DataTable.Td><Errors r={r} /></DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable> : q.isSuccess && <EmptyState>{t("Este brain no ha llamado a ningún motor de IA en los últimos 30 días.")}</EmptyState>}
      <Group align="flex-end" gap="xs">
        <NumberField label={t("Presupuesto mensual")} w={200} min={0} value={limit} onChange={setLimit} placeholder={t("Sin presupuesto")} />
        <Segments label={t("En")} value={unit} onChange={(v) => setUnit(v as "tokens" | "cost")} data={[{ value: "tokens", label: t("Tokens") }, { value: "cost", label: t("Coste estimado") }]} />
        <Btn kind="primary" icon="save" loading={save.isPending} onClick={() => save.mutate()}>{t("Guardar")}</Btn>
      </Group>
      <Check checked={pause} onChange={(e) => setPause(e.currentTarget.checked)} label={t("Pausar la ingesta al agotarlo")}
        description={t("Las propuestas aprobadas esperan, marcadas, y siguen solas al subir el presupuesto o al cambiar de mes. Al 80 % y al 100 % se avisa (ai.budget).")} />
      <MutationError error={save.error} />
    </Stack>
  );
}

/** Consumo de IA de toda la instancia: los motores con su ritmo ahora y sus errores, los precios, y cada brain. */
export function InstanceAiUsage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["ai-usage"], queryFn: () => get<InstanceUsage>("ai-usage", { days: 30 }), refetchInterval: 15000 });
  const [edit, setEdit] = useState<Engine | null>(null); const [pin, setPin] = useState<number | string>(0); const [pout, setPout] = useState<number | string>(0);
  const save = useMutation({ mutationFn: () => send("PUT", "ai-usage/prices", { kind: edit!.kind, model: edit!.model, price_in: Number(pin) || 0, price_out: Number(pout) || 0 }),
    onSuccess: () => { setEdit(null); qc.invalidateQueries({ queryKey: ["ai-usage"] }); } });
  const engines = q.data?.engines ?? []; const brains = q.data?.brains ?? [];
  return (
    <Stack gap="md">
      <Notice tone="info">{t("Últimos 30 días, contados donde MimirSynth llama a cada motor. «Ahora» son las peticiones del último minuto en este proceso; los 429 dicen que el proveedor limita el ritmo, y suelen explicar una ingesta lenta. El coste es una estimación con el precio por millón de tokens de cada modelo.")}</Notice>
      <Modal opened={!!edit} onClose={() => setEdit(null)} title={t("Precio de {{m}}", { m: edit?.model ?? "" })} centered>
        <Stack gap="xs">
          <Group grow><NumberField label={t("Por millón de tokens de entrada")} min={0} decimalScale={4} value={pin} onChange={setPin} />
            <NumberField label={t("Por millón de tokens de salida")} min={0} decimalScale={4} value={pout} onChange={setPout} /></Group>
          <Text size="xs" c="dimmed">{t("Con un motor local (Ollama) déjalo a cero: lo que importa es el tiempo.")}</Text>
          <MutationError error={save.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setEdit(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="save" loading={save.isPending} onClick={() => save.mutate()}>{t("Guardar")}</Btn></Group>
        </Stack>
      </Modal>
      {engines.length ? <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <DataTable.Th>{t("Motor")}</DataTable.Th><DataTable.Th>{t("Ahora (por minuto)")}</DataTable.Th><DataTable.Th>{t("Pico por minuto")}</DataTable.Th>
          <DataTable.Th>{t("Llamadas")}</DataTable.Th><DataTable.Th>{t("Tokens (entrada / salida)")}</DataTable.Th><DataTable.Th>{t("Errores")}</DataTable.Th>
          <DataTable.Th>{t("Precio por millón")}</DataTable.Th><DataTable.ActionsHead />
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{engines.map((e) => (
          <DataTable.Tr key={`${e.kind}:${e.model}`}>
            <DataTable.Td><Text size="xs">{t(KIND[e.kind] ?? e.kind)}</Text><Text size="xs" c="dimmed" className="ms-data">{e.model}</Text></DataTable.Td>
            <DataTable.Td>{e.rpm_now}</DataTable.Td><DataTable.Td>{e.peak_rpm}</DataTable.Td><DataTable.Td>{num(e.calls)}</DataTable.Td>
            <DataTable.Td>{num(e.prompt_tokens)} / {num(e.completion_tokens)}</DataTable.Td><DataTable.Td><Errors r={e} /></DataTable.Td>
            <DataTable.Td>{e.price ? `${money(e.price[0])} / ${money(e.price[1])}` : <Text size="xs" c="dimmed">{t("sin precio")}</Text>}</DataTable.Td>
            <DataTable.Td><Btn size="row" icon="edit" onClick={() => { setPin(e.price?.[0] ?? 0); setPout(e.price?.[1] ?? 0); save.reset(); setEdit(e); }}>{t("Precio")}</Btn></DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable> : q.isSuccess && <EmptyState>{t("Ningún motor ha recibido llamadas en los últimos 30 días.")}</EmptyState>}
      {brains.length > 0 && <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <DataTable.Th>{t("Brain")}</DataTable.Th><DataTable.Th>{t("Llamadas")}</DataTable.Th><DataTable.Th>{t("Tokens")}</DataTable.Th>
          <DataTable.Th>{t("Coste estimado")}</DataTable.Th><DataTable.Th>{t("Errores")}</DataTable.Th>
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{brains.map((b) => (
          <DataTable.Tr key={b.brain_id}>
            <DataTable.Td>{b.brain_id ? b.name || b.slug : <Text size="xs" c="dimmed">{t("Sin brain (pruebas de motores, cambio de modelo)")}</Text>}</DataTable.Td>
            <DataTable.Td>{num(b.calls)}</DataTable.Td><DataTable.Td>{num(b.tokens)}</DataTable.Td>
            <DataTable.Td>{money(b.cost)}{!b.priced && <Text size="xs" c="dimmed">{t("en parte sin precio")}</Text>}</DataTable.Td><DataTable.Td><Errors r={b} /></DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable>}
    </Stack>
  );
}
