import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Brain, fmt, get, send } from "../api";
import { Block, Btn, ConfirmDialog, DataState, DataTable, EmptyState, MutationError, NumberField, Pill, SelectField, ViewBar } from "../ui";

type Side = { slug: string; name: string };
type Grant = { id: number; scope: string; expires_at: string | null; active: boolean; last_used_at: string | null; source: Side; target: Side };
type Grants = { received: Grant[]; given: Grant[] };

const SCOPES = [
  { value: "both", label: T("Grafo y documentos") },
  { value: "graph", label: T("Solo grafo (hechos y episodios)") },
  { value: "docs", label: T("Solo documentos") },
];

/** Federación: qué brains prestan su lectura a este y a cuáles presta este el suyo. Solo lectura, sin transitividad, revocable al instante. A view
 *  inside the settings group that titles it: the bar (the «i» and, for an administrator, the fields of a new grant with «Grant read access»),
 *  then a block per direction, each a table. */
export default function Federation({ brain, canAdmin }: { brain: Brain; canAdmin: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["grants", brain.slug];
  const list = useQuery({ queryKey: key, queryFn: () => get<Grants>(`brains/${brain.slug}/grants`) });
  const brains = useQuery({ queryKey: ["brains"], queryFn: () => get<Brain[]>("brains") });
  const [target, setTarget] = useState<string | null>(null);
  const [scope, setScope] = useState<string | null>("both");
  const [days, setDays] = useState<number | string>("");
  const [ask, setAsk] = useState<Grant | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const create = useMutation({
    mutationFn: () => send("POST", `brains/${brain.slug}/grants`, { target, scope, days: days === "" ? null : Number(days) }),
    onSuccess: () => { setTarget(null); setDays(""); refresh(); } });
  const patch = useMutation({ mutationFn: (v: { id: number; scope: string }) => send("PATCH", `brains/${brain.slug}/grants/${v.id}`, { scope: v.scope }), onSuccess: refresh });
  const revoke = useMutation({ mutationFn: (g: Grant) => send("DELETE", `brains/${brain.slug}/grants/${g.id}`), onSuccess: refresh });
  const scopes = SCOPES.map((s) => ({ ...s, label: t(s.label) }));
  const scopeLabel = (v: string) => scopes.find((s) => s.value === v)?.label ?? v;
  const taken = new Set((list.data?.given ?? []).map((g) => g.target.slug));
  const options = (brains.data ?? []).filter((b) => b.slug !== brain.slug && !taken.has(b.slug)).map((b) => ({ value: b.slug, label: b.name }));
  const expiry = (g: Grant) => g.expires_at ? (g.active ? `${t("hasta")} ${fmt(g.expires_at)}` : t("caducada")) : t("sin caducidad");
  const d = list.data;
  return (
    <>
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)} title={ask?.source.slug === brain.slug ? t("Revocar concesión") : t("Renunciar a la concesión")} action={ask?.source.slug === brain.slug ? t("Revocar") : t("Renunciar")}
        subject={ask && `${ask.source.name} → ${ask.target.name}`}
        warning={t("Surte efecto en la siguiente consulta. Para volver a prestar hay que crear otra concesión.")} onConfirm={() => revoke.mutateAsync(ask!)} />
      <ViewBar title={t("Federación")}
        help={t("Un brain presta a otro su memoria solo para leer: las consultas del que recibe incluyen lo prestado, fusionado y marcado con su origen. No se comparten embeddings ni resúmenes, y la concesión no se transmite a un tercero.")}
        actions={canAdmin && <Btn kind="primary" icon="plus" disabled={!target || !scope} loading={create.isPending} onClick={() => create.mutate()}>{t("Conceder lectura")}</Btn>}>
        {canAdmin && <>
          <SelectField label={t("Prestar a")} data={options} value={target} onChange={setTarget} placeholder={t("Elige un brain")} />
          <SelectField label={t("Qué presta")} data={scopes} value={scope} onChange={setScope} allowDeselect={false} />
          <NumberField label={t("Días de vigencia")} placeholder={t("sin caducidad")} min={1} max={3650} value={days} onChange={setDays} />
        </>}
      </ViewBar>
      <MutationError error={create.error ?? patch.error ?? revoke.error} />
      {!d ? <DataState query={list} /> : <>
        {canAdmin && <Block title={t("Este brain presta su lectura a")} count={d.given.length}>
          {d.given.length ? <DataTable fz="sm" aria-label={t("Este brain presta su lectura a")}>
            <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Brain")}</DataTable.Th><DataTable.Th>{t("Qué presta")}</DataTable.Th><DataTable.Th>{t("Vigencia")}</DataTable.Th><DataTable.Th>{t("Último uso")}</DataTable.Th><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{d.given.map((g) => (
              <DataTable.Tr key={g.id}>
                <DataTable.Td>{g.target.name}</DataTable.Td>
                <DataTable.Td><SelectField aria-label={t("Qué presta")} data={scopes} value={g.scope} allowDeselect={false} onChange={(v) => v && patch.mutate({ id: g.id, scope: v })} /></DataTable.Td>
                <DataTable.Td>{g.active ? expiry(g) : <Pill tone="warn">{expiry(g)}</Pill>}</DataTable.Td>
                <DataTable.Td className="ms-data">{g.last_used_at ? fmt(g.last_used_at) : t("nunca")}</DataTable.Td>
                <DataTable.Td><Btn kind="danger" size="row" icon="trash" onClick={() => setAsk(g)}>{t("Revocar")}</Btn></DataTable.Td>
              </DataTable.Tr>))}</DataTable.Tbody>
          </DataTable> : <EmptyState>{t("No presta su memoria a ningún brain.")}</EmptyState>}
        </Block>}
        <Block title={t("Este brain recibe lectura de")} count={d.received.length}>
          {d.received.length ? <DataTable fz="sm" aria-label={t("Este brain recibe lectura de")}>
            <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Brain")}</DataTable.Th><DataTable.Th>{t("Qué presta")}</DataTable.Th><DataTable.Th>{t("Vigencia")}</DataTable.Th>{canAdmin && <DataTable.ActionsHead />}</DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{d.received.map((g) => (
              <DataTable.Tr key={g.id}>
                <DataTable.Td>{g.source.name}</DataTable.Td>
                <DataTable.Td>{scopeLabel(g.scope)}</DataTable.Td>
                <DataTable.Td>{g.active ? expiry(g) : <Pill tone="warn">{expiry(g)}</Pill>}</DataTable.Td>
                {canAdmin && <DataTable.Td><Btn kind="danger" size="row" icon="trash" onClick={() => setAsk(g)}>{t("Renunciar")}</Btn></DataTable.Td>}
              </DataTable.Tr>))}</DataTable.Tbody>
          </DataTable> : <EmptyState>{t("Ningún brain presta su memoria a este.")}</EmptyState>}
        </Block>
      </>}
    </>
  );
}
