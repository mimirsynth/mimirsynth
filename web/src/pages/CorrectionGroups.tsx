import { useTranslation } from "react-i18next";
import { Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, fmtDay, get, send } from "../api";
import { Block, Btn, CellText, Check, DataTable, DialogActions, ListCard, Modal, MutationError, Notice, Pill, TextArea } from "../ui";

type Fact = { fact: string; source: string; target: string; valid_at: string | null; invalid_at?: string | null };
type Row = { id: number; name: string; fact_uuid: string; fact: Fact; reason: string; replacement: string; flagged: boolean; secrets: { label: string }[] };
type Group = { key: string; author: string; token: boolean; source_description: string; count: number; first_at: string; last_at: string; items: Row[] };
type Decided = { approved: number[]; rejected: number[]; skipped: { id: number; reason: string; detail?: string }[] };

/** Corrections sent together (issue 457): pending invalidations with the same author, token and origin, reviewed as one table instead of
 *  one at a time. Approving applies the ticked ones, each as its own correction (same audit, same undo); the unticked ones are rejected with
 *  the group's note. One with a secret to review is left out, to be decided alone. */
export default function CorrectionGroups({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["correction-groups", graph], refetchInterval: 15000, queryFn: () => get<{ groups: Group[] }>(`brains/${graph}/correction-groups`) });
  const [open, setOpen] = useState<Group | null>(null);
  const [done, setDone] = useState<Decided | null>(null);
  const groups = q.data?.groups ?? [];
  if (!groups.length && !done) return null;
  return (<>
    {done && <DoneNotice d={done} onClose={() => setDone(null)} />}
    {groups.length > 0 && <Block title={t("Correcciones enviadas juntas")} count={groups.length}
      help={t("Correcciones pendientes con el mismo autor y el mismo origen: se revisan juntas, en una tabla, en lugar de una a una. Aprobar aplica las marcadas, cada una como su propia corrección, que se deshace aparte; las desmarcadas se rechazan con la nota del grupo. Siguen también en la cola, por si prefieres decidir alguna sola.")}>
      <Stack gap="sm">
        {groups.map((g) => (
          <ListCard key={g.key} title={t("{{n}} correcciones de {{author}}", { n: g.count, author: g.author })} aside={fmt(g.last_at)}
            note={<>{t("Origen:")} «{g.source_description}»{g.token ? ` · ${t("enviadas con un token")}` : ""}</>}
            actions={<Btn kind="primary" size="row" onClick={() => setOpen(g)}>{t("Revisar el grupo")}</Btn>} />))}
      </Stack>
    </Block>}
    {open && <GroupDialog graph={graph} g={open} onClose={() => setOpen(null)} onDone={(d) => { setDone(d); setOpen(null); }} />}
  </>);
}

function DoneNotice({ d, onClose }: { d: Decided; onClose: () => void }) {
  const { t } = useTranslation();
  const why = (s: Decided["skipped"][number]) => (s.reason === "secret" ? t("tiene un posible secreto: decídela aparte") : s.detail || t("su hecho cambió mientras tanto"));
  return (
    <Notice tone={d.skipped.length ? "warn" : "success"} title={t("Grupo decidido")} withCloseButton onClose={onClose}>
      {t("Aplicadas: {{a}}. Rechazadas: {{r}}.", { a: d.approved.length, r: d.rejected.length })}
      {d.skipped.length > 0 && <> {t("Siguen pendientes:")} {d.skipped.map((s) => `#${s.id} (${why(s)})`).join("; ")}.</>}
    </Notice>
  );
}

function GroupDialog({ graph, g, onClose, onDone }: { graph: string; g: Group; onClose: () => void; onDone: (d: Decided) => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const decidable = g.items.filter((r) => !r.flagged);
  const [ticked, setTicked] = useState<Set<number>>(new Set(decidable.map((r) => r.id)));
  const [note, setNote] = useState("");
  const approve = decidable.filter((r) => ticked.has(r.id)).map((r) => r.id);
  const reject = decidable.filter((r) => !ticked.has(r.id)).map((r) => r.id);
  const decide = useMutation({ mutationFn: () => send<Decided>("POST", `brains/${graph}/correction-groups/decide`, { approve, reject, note }),
    onSuccess: (d) => { ["proposals", "correction-groups", "entity"].forEach((k) => qc.invalidateQueries({ queryKey: [k, graph] })); onDone(d); } });
  const toggle = (id: number, on: boolean) => setTicked((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n; });
  const when = (f: Fact) => (f.invalid_at ? t("válido {{from}} → {{to}}", { from: fmtDay(f.valid_at), to: fmtDay(f.invalid_at) })
    : f.valid_at ? t("vigente desde {{date}}", { date: fmtDay(f.valid_at) }) : "");
  return (
    <Modal opened onClose={onClose} size="xl" title={t("{{n}} correcciones de {{author}}", { n: g.count, author: g.author })}>
      <Stack gap="md">
        <Text size="sm">{t("Origen:")} «{g.source_description}». {t("Cada fila marcada invalida su hecho al aprobar; las desmarcadas se rechazan con la nota.")}</Text>
        {g.items.length < g.count && <Notice tone="warn" title={t("Se muestran {{n}} de {{all}}", { n: g.items.length, all: g.count })}>{t("Las demás siguen en la cola y en el grupo para la próxima vez.")}</Notice>}
        <DataTable fz="sm" aria-label={t("Correcciones del grupo")}>
          <DataTable.Thead><DataTable.Tr>
            <DataTable.Th><Check aria-label={t("Marcar todas")} checked={approve.length === decidable.length && decidable.length > 0}
              indeterminate={approve.length > 0 && approve.length < decidable.length} onChange={(e) => setTicked(new Set(e.currentTarget.checked ? decidable.map((r) => r.id) : []))} /></DataTable.Th>
            <DataTable.Th>{t("Hecho que se invalida")}</DataTable.Th><DataTable.Th>{t("Motivo")}</DataTable.Th><DataTable.Th>{t("Lo que lo sustituye")}</DataTable.Th>
          </DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>
            {g.items.map((r) => (
              <DataTable.Tr key={r.id}>
                <DataTable.Td>{r.flagged ? <Pill tone="warn" title={r.secrets.map((s) => s.label).join(", ")}>{t("aparte")}</Pill>
                  : <Check aria-label={t("Aprobar #{{id}}", { id: r.id })} checked={ticked.has(r.id)} onChange={(e) => toggle(r.id, e.currentTarget.checked)} />}</DataTable.Td>
                <DataTable.Td><CellText sub={<>#{r.id} · {r.fact.source} → {r.fact.target} · {when(r.fact)} · <span className="ms-data">{(r.fact_uuid || "").slice(0, 8)}</span></>}>
                  {r.fact.fact}</CellText></DataTable.Td>
                <DataTable.Td><Text inherit className="ms-wrap-any">{r.reason}</Text></DataTable.Td>
                <DataTable.Td>{r.replacement.trim() ? <Text inherit className="ms-wrap-any">{r.replacement}</Text> : "—"}</DataTable.Td>
              </DataTable.Tr>))}
          </DataTable.Tbody>
        </DataTable>
        {g.items.some((r) => r.flagged) && <Text size="sm">{t("Las marcadas «aparte» tienen un posible secreto: se quedan pendientes y se deciden una a una, enmascarándolo.")}</Text>}
        <TextArea label={t("Nota del grupo")} description={t("Se guarda en todas: en las aprobadas como nota de la decisión y en las rechazadas como motivo.")}
          autosize minRows={2} maxRows={6} maxLength={2000} value={note} onChange={(e) => setNote(e.currentTarget.value)} />
        <Notice tone="warn" title={t("Qué hará")}>{t("Hechos que se invalidan, cada uno con su propia corrección, que se puede reactivar por separado: {{n}}.", { n: approve.length })}{reject.length ? ` ${t("Se rechazan {{m}}.", { m: reject.length })}` : ""}</Notice>
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
