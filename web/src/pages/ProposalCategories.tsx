import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, CellText, ConfirmDialog, DataState, DataTable, EmptyState, ListCard, MutationError, Notice, Pill, Toggle, ViewBar } from "../ui";
import { T } from "../i18n";

type Sample = { id: number; name: string; body: string; created_at: string; claims: { subject: string; relation: string; value: string; verdict: string; facts: string[] }[] };
type Cat = { category: string; pending: number; oldest: string | null; flagged: number; sample: Sample[];
  precision: { decided: number; approved: number; precision: number | null }; auto: { enabled: boolean; bar: number; min: number } };

/** How each category reads: what produced its proposals. An unknown one shows its id. */
const LABEL: Record<string, string> = {
  "curator.contradictions": T("Contradicciones que propone el curador"), "curator.distil": T("Notas destiladas por el curador (se aprueban una a una)"), "forget.rewrite": T("Episodios reescritos sin datos personales"), "verifier.refuted": T("Hechos que un verificador contradice"),
  correction: T("Correcciones"), duplicate: T("Posibles duplicados"), stale: T("Parecidas a algo que ya no es cierto"), new: T("Nuevas"),
};

/** The review queue by category (issue 299): decide a whole category after a look at its sample, and the tiers that approve one on their own.
 *  A view of the Proposals page: its bar (what it is for, behind the «i»), then one list card per category (its sample as a table, its
 *  precision as the note, the decision and the admin's auto-approve switch as its actions). */
export default function ProposalCategories({ graph, isAdmin }: { graph: string; isAdmin: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["proposals", graph, "categories"];
  const q = useQuery({ queryKey: key, queryFn: () => get<{ items: Cat[] }>(`brains/${graph}/review/categories`) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["proposals", graph] });
  const [ask, setAsk] = useState<{ cat: Cat; verb: "approve" | "reject" } | null>(null);
  const decide = useMutation({ mutationFn: (a: { cat: Cat; verb: "approve" | "reject" }) => send<{ done: number[]; skipped: unknown[]; left: number }>("POST",
    `brains/${graph}/review/categories/${encodeURIComponent(a.cat.category)}/decide`, { verb: a.verb, seen: a.cat.sample.map((s) => s.id) }), onSuccess: () => { setAsk(null); refresh(); } });
  const tier = useMutation({ mutationFn: (a: { cat: Cat; enabled: boolean }) => send("PUT", `brains/${graph}/review/categories/${encodeURIComponent(a.cat.category)}/auto`,
    { enabled: a.enabled, bar: a.cat.auto.bar, min: a.cat.auto.min }), onSuccess: refresh });
  const items = q.data?.items ?? [];
  return (<>
    <ViewBar title={t("Por categorías")}
      help={t("Lo pendiente agrupado por lo que lo produjo. Mira la muestra de una categoría y apruébala o recházala entera; lo que tiene un secreto por revisar y las correcciones se quedan para decidirlas una a una. La precisión es la parte de sus propuestas que aprobaron los curadores; con la suficiente, un administrador puede hacer que la categoría se apruebe sola.")} />
    <MutationError error={decide.error ?? tier.error} />
    {decide.data && <Notice tone="success">{t("Decididas: {{n}}.", { n: decide.data.done.length })}{decide.data.left ? ` ${t("Quedan {{n}} para otra vez.", { n: decide.data.left })}` : ""}</Notice>}
    {!q.data ? <DataState query={q} /> : !items.length && <EmptyState>{t("No hay nada pendiente.")}</EmptyState>}
    {items.map((c) => {
      const p = c.precision;
      const earned = p.decided >= c.auto.min && (p.precision ?? 0) >= c.auto.bar;
      const claims = c.sample.some((s) => s.claims.length > 0);
      return (<ListCard key={c.category} title={t(LABEL[c.category] ?? c.category)}
        aside={<><Pill tone={c.pending ? "warn" : "neutral"}>{c.pending}</Pill>{c.auto.enabled && <Pill tone="success">{t("Se aprueba sola")}</Pill>}</>}
        note={<>{p.precision === null ? t("Ninguna decidida todavía por una persona.")
          : t("Precisión: {{pct}} ({{a}} aprobadas de {{d}} decididas por personas).", { pct: `${Math.round(p.precision * 100)} %`, a: p.approved, d: p.decided })}
          {c.flagged ? ` ${t("{{n}} con un secreto por revisar, que no se deciden en bloque.", { n: c.flagged })}` : ""}</>}
        meta={[c.oldest ? t("la más antigua: {{at}}", { at: fmt(c.oldest) }) : "",
          c.pending > c.sample.length && c.sample.length > 0 ? t("Muestra de {{n}} de {{total}}.", { n: c.sample.length, total: c.pending }) : ""].filter(Boolean).join(" · ") || undefined}
        actions={(c.pending > 0 || isAdmin) ? <>
          {c.pending > 0 && <>
            <Btn size="row" icon="check" onClick={() => setAsk({ cat: c, verb: "approve" })}>{t("Aprobar la categoría")}</Btn>
            <Btn size="row" kind="danger" onClick={() => setAsk({ cat: c, verb: "reject" })}>{t("Rechazar la categoría")}</Btn>
          </>}
          {isAdmin && <Toggle checked={c.auto.enabled} disabled={!c.auto.enabled && !earned} onChange={(e) => tier.mutate({ cat: c, enabled: e.currentTarget.checked })}
            label={t("Aprobar esta categoría automáticamente")}
            description={t("Solo con al menos {{min}} decisiones de personas y una precisión de {{bar}}. Si baja, vuelve a ser manual y avisa. Nunca aprueba lo que tiene un secreto por revisar.", { min: c.auto.min, bar: `${Math.round(c.auto.bar * 100)} %` })} />}
        </> : undefined}>
        {c.sample.length > 0 && <DataTable fz="sm" aria-label={t("Muestra de la categoría")}>
          <DataTable.Thead><DataTable.Tr>
            <DataTable.Th>#</DataTable.Th><DataTable.Th>{t("Propuesta")}</DataTable.Th>{claims && <DataTable.Th>{t("Afirmaciones")}</DataTable.Th>}
          </DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>
            {c.sample.map((s) => <DataTable.Tr key={s.id}>
              <DataTable.Td className="ms-data">#{s.id}</DataTable.Td>
              <DataTable.Td><CellText sub={s.body ? <span className="ms-clamp" title={s.body}>{s.body}</span> : undefined}>{s.name}</CellText></DataTable.Td>
              {claims && <DataTable.Td>{s.claims.map((cl) => `${cl.subject} → ${cl.relation} → ${cl.value}${cl.facts.length ? ` (${cl.facts.join("; ")})` : ""}`).join(" · ") || "—"}</DataTable.Td>}
            </DataTable.Tr>)}
          </DataTable.Tbody>
        </DataTable>}
      </ListCard>);
    })}
    <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)}
      title={ask?.verb === "approve" ? t("¿Aprobar toda la categoría?") : t("¿Rechazar toda la categoría?")}
      action={ask?.verb === "approve" ? t("Aprobar") : t("Rechazar")} tone={ask?.verb === "approve" ? "primary" : "danger"}
      onConfirm={() => (ask ? decide.mutateAsync(ask) : Promise.resolve())}>
      {ask && t("Se deciden sus {{n}} propuestas pendientes (hasta 200), las hayas visto o no, salvo las que tienen un secreto por revisar y las correcciones.", { n: ask.cat.pending })}
    </ConfirmDialog>
  </>);
}
