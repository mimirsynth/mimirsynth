import { useTranslation } from "react-i18next";
import { Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { fmt, fmtDay, get, send } from "../api";
import { Block, Btn, CellText, DataState, DataTable, DialogActions, EmptyState, Modal, MutationError, Notice, PasswordField, Pill, SelectField, SettingsBody, SettingsGroup, SettingsRow, Sheet, SheetRow, TextField, ViewBar, type Tone } from "../ui";
import { T } from "../i18n";

/** A verifier this instance has (issue 293): its per-brain settings (secret ones never come back, only whether they are set) and what each probe asks. */
export type Verifier = { id: string; label: string;
  config: { name: string; label: string; secret: boolean; required: boolean; help: string; set: boolean; value?: string }[];
  params: { name: string; label: string; required: boolean; help: string }[] };
export type Probe = { fact_uuid: string; verifier: string; params: Record<string, string>; state: string | null; evidence: string; value: string | null;
  checked_at: string | null; created_at: string; fact?: string | null; source?: string | null; source_uuid?: string | null; invalid_at?: string | null };

const STATE: Record<string, { label: string; tone: Tone }> = {
  verified: { label: T("Verificado"), tone: "success" }, refuted: { label: T("Refutado"), tone: "danger" },
  unverifiable: { label: T("No verificable"), tone: "neutral" }, pending: { label: T("Sin comprobar"), tone: "neutral" },
};

/** The brain's probes by fact, to show next to each fact. Only for curators, who can read them. */
export function useProbes(graph: string, enabled: boolean) {
  const q = useQuery({ queryKey: ["probes", graph], enabled, queryFn: () => get<{ items: Probe[] }>(`brains/${graph}/probes`) });
  return new Map((q.data?.items ?? []).map((p) => [p.fact_uuid, p]));
}

/** A probe's last result, as a small mark with its evidence in the tooltip. */
export function ProbeMark({ p }: { p: Probe }) {
  const { t } = useTranslation();
  const s = STATE[p.state ?? "pending"] ?? STATE.pending;
  return <span title={p.evidence || undefined}><Pill size="xs" tone={s.tone}>{t(s.label)}{p.checked_at ? ` · ${fmtDay(p.checked_at)}` : ""}</Pill></span>;
}

/** Attach, change or remove the probe of one current fact: which verifier checks it and with what. */
export function ProbeDialog({ graph, fact, probe, onClose }: { graph: string; fact: { uuid: string; fact: string }; probe?: Probe; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const vs = useQuery({ queryKey: ["verifiers", graph], queryFn: () => get<{ items: Verifier[] }>(`brains/${graph}/verifiers`) });
  const [vid, setVid] = useState<string>(probe?.verifier ?? "");
  const [params, setParams] = useState<Record<string, string>>(probe?.params ?? {});
  const v = vs.data?.items.find((x) => x.id === (vid || vs.data?.items[0]?.id));
  const done = () => { qc.invalidateQueries({ queryKey: ["probes", graph] }); onClose(); };
  const save = useMutation({ mutationFn: () => send("PUT", `brains/${graph}/facts/${fact.uuid}/probe`, { verifier: v?.id, params }), onSuccess: done });
  const remove = useMutation({ mutationFn: () => send("DELETE", `brains/${graph}/facts/${fact.uuid}/probe`), onSuccess: done });
  const unset = v?.config.filter((c) => c.required && !c.set) ?? [];
  return (
    <Modal opened onClose={onClose} title={t("Sonda del hecho")}>
      <Stack gap="sm">
        <Text size="sm">«{fact.fact}»</Text>
        <Text size="sm" c="dimmed">{t("Un verificador lo comprobará contra un sistema una vez al día. Si se confirma, se renueva su fecha; si lo contradice, se crea una propuesta para que la decida una persona.")}</Text>
        {probe && <Sheet label={t("Último resultado")}><SheetRow term={<ProbeMark p={probe} />}>{probe.evidence || "—"}</SheetRow></Sheet>}
        {vs.data && <SelectField label={t("Verificador")} data={vs.data.items.map((x) => ({ value: x.id, label: t(x.label) }))} value={v?.id ?? null}
          onChange={(x) => { setVid(x ?? ""); setParams({}); }} allowDeselect={false} />}
        {v?.params.map((p) => <TextField key={p.name} label={t(p.label)} description={p.help ? t(p.help) : undefined} required={p.required}
          value={params[p.name] ?? ""} onChange={(e) => setParams({ ...params, [p.name]: e.currentTarget.value })} />)}
        {unset.length > 0 && <Notice tone="warn">{t("Este verificador aún no está configurado en el brain ({{v}}): un administrador lo hace en Calidad del contenido → Verificación.", { v: unset.map((c) => t(c.label)).join(", ") })}</Notice>}
        <MutationError error={save.error ?? remove.error} />
        <DialogActions>
          <Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn>
          {probe && <Btn kind="danger" loading={remove.isPending} onClick={() => remove.mutate()}>{t("Quitar la sonda")}</Btn>}
          <Btn kind="primary" loading={save.isPending} disabled={!v || v.params.some((p) => p.required && !(params[p.name] ?? "").trim())} onClick={() => save.mutate()}>{t("Guardar")}</Btn>
        </DialogActions>
      </Stack>
    </Modal>
  );
}

/** One verifier's settings for this brain, for its administrators, as a settings group with a row per setting: a secret left empty
 *  keeps the stored one. */
function VerifierSettings({ graph, v }: { graph: string; v: Verifier }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>(Object.fromEntries(v.config.map((c) => [c.name, c.secret ? "" : c.value ?? ""])));
  const save = useMutation({ mutationFn: () => send("PUT", `brains/${graph}/verifiers/${v.id}`, { values }), onSuccess: () => qc.invalidateQueries({ queryKey: ["verifiers", graph] }) });
  const set = (name: string, value: string) => { save.reset(); setValues({ ...values, [name]: value }); };
  return (
    <SettingsGroup title={t(v.label)} description={<span className="ms-data">{v.id}</span>}
      action={v.config.length > 0 && <Btn size="row" icon={save.isSuccess ? "check" : undefined} loading={save.isPending} onClick={() => save.mutate()}>{save.isSuccess ? t("Guardado") : t("Guardar ajustes")}</Btn>}>
      {v.config.length ? v.config.map((c) => (
        <SettingsRow key={c.name} label={t(c.label)} help={c.secret && c.set ? t("Guardado. Déjalo vacío para conservarlo.") : c.help ? t(c.help) : undefined}>
          {c.secret
            ? <PasswordField aria-label={t(c.label)} value={values[c.name] ?? ""} onChange={(e) => set(c.name, e.currentTarget.value)} />
            : <TextField aria-label={t(c.label)} value={values[c.name] ?? ""} onChange={(e) => set(c.name, e.currentTarget.value)} />}
        </SettingsRow>))
        : <SettingsBody><EmptyState>{t("No necesita ajustes.")}</EmptyState></SettingsBody>}
      {save.error ? <SettingsBody><MutationError error={save.error} /></SettingsBody> : null}
    </SettingsGroup>
  );
}

/** Content quality → Verification (issue 293): every probe of the brain with its last result, checking them now, and the verifiers' settings. */
export default function ProbesPanel({ graph, isAdmin }: { graph: string; isAdmin: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const probes = useQuery({ queryKey: ["probes", graph], queryFn: () => get<{ items: Probe[] }>(`brains/${graph}/probes`) });
  const vs = useQuery({ queryKey: ["verifiers", graph], queryFn: () => get<{ items: Verifier[] }>(`brains/${graph}/verifiers`) });
  const run = useMutation({ mutationFn: () => send("POST", `brains/${graph}/probes/run`), onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["probes", graph] }), 3000) });
  const items = probes.data?.items ?? [];
  return (
    <>
      <ViewBar title={t("Verificación")}
        help={t("Una sonda comprueba un hecho contra un sistema vivo una vez al día mediante un verificador. Se pone desde la página de cada entidad, en el hecho («Sonda»). Un hecho verificado renueva su fecha; uno refutado se convierte en una propuesta que decide una persona; nada cambia por su cuenta.")}
        actions={<><Btn kind="link" component={Link} to="/propuestas">{t("Ver las propuestas de los verificadores")}</Btn>
          <Btn kind="primary" icon="refresh" disabled={!items.length} loading={run.isPending} onClick={() => run.mutate()}>{t("Comprobar ahora")}</Btn></>} />
      <MutationError error={run.error} />
      {!probes.data ? <DataState query={probes} /> : items.length ? (
        <DataTable aria-label={t("Sondas")}>
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Hecho")}</DataTable.Th><DataTable.Th>{t("Verificador")}</DataTable.Th><DataTable.Th>{t("Resultado")}</DataTable.Th><DataTable.Th>{t("Comprobado")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{items.map((p) => <DataTable.Tr key={p.fact_uuid}>
            <DataTable.Td><CellText sub={<>{p.source_uuid && <Link to={`/entidad/${p.source_uuid}`}>{p.source}</Link>}{p.invalid_at ? ` · ${t("ya no está vigente")}` : ""}</>}>
              {p.fact ? `«${p.fact}»` : <span className="ms-data">{p.fact_uuid}</span>}</CellText></DataTable.Td>
            <DataTable.Td><CellText data sub={Object.keys(p.params).length ? Object.entries(p.params).map(([k, x]) => `${k}: ${x}`).join(", ") : undefined}>{p.verifier}</CellText></DataTable.Td>
            <DataTable.Td><CellText sub={p.evidence || undefined}><ProbeMark p={p} /></CellText></DataTable.Td>
            <DataTable.Td className="ms-data">{p.checked_at ? fmt(p.checked_at) : "—"}</DataTable.Td>
          </DataTable.Tr>)}</DataTable.Tbody>
        </DataTable>)
        : <EmptyState>{t("Ningún hecho tiene sonda todavía.")}</EmptyState>}
      {isAdmin && vs.data && vs.data.items.length > 0 && <Block title={t("Verificadores de esta instancia")}
        help={t("Los verificadores propios se cargan de la carpeta MIMIRSYNTH_VERIFIERS_DIR al arrancar; los ajustes secretos se guardan cifrados y nunca se muestran.")}>
        {vs.data.items.map((v) => <VerifierSettings key={v.id} graph={graph} v={v} />)}
      </Block>}
    </>
  );
}
