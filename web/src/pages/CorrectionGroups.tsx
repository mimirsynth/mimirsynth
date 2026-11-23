import { useTranslation } from "react-i18next";
import { Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmtDay, get, send } from "../api";
import { Btn, CellText, Check, DataTable, DialogActions, Icon, Modal, MutationError, Notice, Pill, TextArea } from "../ui";

type Fact = { fact: string; source: string; target: string; valid_at: string | null; invalid_at?: string | null };
type Row = { id: number; name: string; fact_uuid: string; fact: Fact; reason: string; replacement: string; replacement_cut?: boolean; flagged: boolean;
  apart?: "secret" | "long" | null; secrets: { label: string }[] };
export type Group = { key: string; author: string; token: boolean; source_description: string; count: number; first_at: string; last_at: string; items: Row[] };
export type Decided = { approved: number[]; rejected: number[]; skipped: { id: number; reason: string; detail?: string }[] };

/** Corrections sent together (issue 457): pending invalidations with the same author, token and origin, reviewed as one table instead of
 *  one at a time. The queue says which ones they are inside its pending-corrections notice; approving applies the ticked ones, each as its
 *  own correction (same audit, same undo), and rejects the unticked ones with the group's note. One with a secret to review is decided alone. */
export function useCorrectionGroups(graph: string) {
  const q = useQuery({ queryKey: ["correction-groups", graph], refetchInterval: 15000, queryFn: () => get<{ groups: Group[] }>(`brains/${graph}/correction-groups`) });
  return q.data?.groups ?? [];
}

/** One line per group, for the pending-corrections notice: who sent them, the origin, which entries of the queue they are, and how long ago. */
export function GroupLines({ groups, ago, onOpen }: { groups: Group[]; ago: (iso: string) => string; onOpen: (g: Group) => void }) {
  const { t } = useTranslation();
  return <Stack gap={4}>{groups.map((g) => (
    <div key={g.key} className="ms-group-line">
      <span>{t("{{n}} enviadas juntas por {{author}} («{{source}}»):", { n: g.count, author: g.author, source: g.source_description })}{" "}
        <span className="ms-data">{g.items.map((r) => `#${r.id}`).join(", ")}{g.items.length < g.count ? "…" : ""}</span> · {ago(g.last_at)}</span>
      <Btn size="row" onClick={() => onOpen(g)}>{t("Revisar juntas")}</Btn>
    </div>))}</Stack>;
}

export function DoneNotice({ d, onClose }: { d: Decided; onClose: () => void }) {
  const { t } = useTranslation();
  const why = (s: Decided["skipped"][number]) => (s.reason === "secret" ? t("tiene un posible secreto: decídela aparte")
    : s.reason === "long" ? t("su sustituto es más largo de lo que muestra la tabla: decídela aparte")
    : s.reason === "not_pending" ? t("otra persona la decidió mientras tanto") : s.reason === "error" ? t("no se pudo aplicar ahora; sigue pendiente")
      : s.detail || t("su hecho cambió mientras tanto"));
  return (
    <Notice tone={d.skipped.length ? "warn" : "success"} title={t("Grupo decidido")} withCloseButton onClose={onClose}>
      {t("Aplicadas: {{a}}. Rechazadas: {{r}}.", { a: d.approved.length, r: d.rejected.length })}
      {d.skipped.length > 0 && <> {t("Siguen pendientes:")} {d.skipped.map((s) => `#${s.id} (${why(s)})`).join("; ")}.</>}
    </Notice>
  );
}

export function GroupDialog({ graph, g, onClose, onDone }: { graph: string; g: Group; onClose: () => void; onDone: (d: Decided) => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const alone = (r: Row) => r.flagged || !!r.apart;
  const decidable = g.items.filter((r) => !alone(r));
  const [ticked, setTicked] = useState<Set<number>>(new Set(decidable.map((r) => r.id)));
  const [note, setNote] = useState("");
  const approve = decidable.filter((r) => ticked.has(r.id)).map((r) => r.id);
  const reject = decidable.filter((r) => !ticked.has(r.id)).map((r) => r.id);
  const decide = useMutation({ mutationFn: () => send<Decided>("POST", `brains/${graph}/correction-groups/decide`, { approve, reject, note }),
    onSettled: () => ["proposals", "correction-groups", "entity"].forEach((k) => qc.invalidateQueries({ queryKey: [k, graph] })),   // also after an error: the table is read again
    onSuccess: (d) => onDone(d) });
  const toggle = (id: number, on: boolean) => setTicked((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n; });
  const when = (f: Fact) => (f.invalid_at ? t("válido {{from}} → {{to}}", { from: fmtDay(f.valid_at), to: fmtDay(f.invalid_at) })
    : f.valid_at ? t("vigente desde {{date}}", { date: fmtDay(f.valid_at) }) : "");
  return (
    <Modal opened onClose={onClose} size="xl" title={t("{{n}} correcciones de {{author}}", { n: g.count, author: g.author })}>
      <Stack gap="md">
        <CellText sub={t("Las marcadas se aprueban y las desmarcadas se rechazan.")}>{t("Origen:")} «{g.source_description}»</CellText>
        {g.items.length < g.count && <Notice tone="warn" title={t("Se muestran {{n}} de {{all}}", { n: g.items.length, all: g.count })}>{t("Las demás siguen en la cola y en el grupo para la próxima vez.")}</Notice>}
        <DataTable fz="sm" aria-label={t("Correcciones del grupo")}>
          <DataTable.Thead><DataTable.Tr>
            <DataTable.Th><Check label={t("Aprobar")} aria-label={t("Aprobar todas")} checked={approve.length === decidable.length && decidable.length > 0}
              indeterminate={approve.length > 0 && approve.length < decidable.length} onChange={(e) => setTicked(new Set(e.currentTarget.checked ? decidable.map((r) => r.id) : []))} /></DataTable.Th>
            <DataTable.Th>{t("Hecho que se invalida")}</DataTable.Th><DataTable.Th>{t("Motivo")}</DataTable.Th><DataTable.Th>{t("Lo que lo sustituye")}</DataTable.Th>
          </DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>
            {g.items.map((r) => (
              <DataTable.Tr key={r.id}>
                <DataTable.Td>{alone(r) ? null
                  : <Check aria-label={t("Aprobar #{{id}}", { id: r.id })} checked={ticked.has(r.id)} onChange={(e) => toggle(r.id, e.currentTarget.checked)} />}</DataTable.Td>
                <DataTable.Td><CellText sub={<>#{r.id} · {r.fact.source} → {r.fact.target} · {when(r.fact)} · <span className="ms-data">{(r.fact_uuid || "").slice(0, 8)}</span>
                  {r.flagged && <> <Pill tone="warn" title={r.secrets.map((s) => s.label).join(", ")}><span className="ms-pill-row"><Icon name="lock" size={12} />{t("Secreto por revisar")}</span></Pill> {t("se decide aparte")}</>}
                  {!r.flagged && r.apart === "long" && <> <Pill tone="warn">{t("Sustituto largo")}</Pill> {t("se decide aparte: la tabla no lo muestra entero")}</>}</>}>
                  {r.fact.fact}</CellText></DataTable.Td>
                <DataTable.Td><Text inherit className="ms-wrap-any">{r.reason}</Text></DataTable.Td>
                <DataTable.Td>{r.replacement.trim() ? <Text inherit className="ms-wrap-any">{r.replacement}{r.replacement_cut ? "…" : ""}</Text> : "—"}</DataTable.Td>
              </DataTable.Tr>))}
          </DataTable.Tbody>
        </DataTable>
        <TextArea label={t("Nota del grupo")} description={t("Se guarda en todas: en las aprobadas como nota de la decisión y en las rechazadas como motivo.")}
          autosize minRows={2} maxRows={6} maxLength={2000} value={note} onChange={(e) => setNote(e.currentTarget.value)} />
        <Notice tone="warn" title={t("Qué hará")}>
          {approve.length === 1 ? t("Se invalida 1 hecho, con su propia corrección, que se puede reactivar aparte.") : approve.length > 1 ? t("Se invalidan {{n}} hechos, cada uno con su propia corrección, que se puede reactivar aparte.", { n: approve.length }) : ""}{" "}
          {reject.length === 1 ? t("Se rechaza 1.") : reject.length > 1 ? t("Se rechazan {{m}}.", { m: reject.length }) : ""}{" "}
          {g.items.some(alone) && t("Se quedan pendientes, para decidirlas aparte: {{ids}}.", { ids: g.items.filter(alone).map((r) => `#${r.id}`).join(", ") })}
        </Notice>
        <MutationError error={decide.error} />
        <DialogActions>
          <Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn>
          <Btn kind="primary" icon="check" loading={decide.isPending} disabled={!approve.length && !reject.length} onClick={() => decide.mutate()}>
            {reject.length ? t("Aprobar {{n}} y rechazar {{m}}", { n: approve.length, m: reject.length }) : t("Aprobar {{n}}", { n: approve.length })}</Btn>
        </DialogActions>
      </Stack>
    </Modal>
  );
}
