import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, Check, ConfirmDialog, EmptyState, MutationError, Notice, Panel, Pill } from "../ui";
import { T } from "../i18n";

type Sample = { id: number; name: string; body: string; created_at: string; claims: { subject: string; relation: string; value: string; verdict: string; facts: string[] }[] };
type Cat = { category: string; pending: number; oldest: string | null; flagged: number; sample: Sample[];
  precision: { decided: number; approved: number; precision: number | null }; auto: { enabled: boolean; bar: number; min: number } };

/** How each category reads: what produced its proposals. An unknown one shows its id. */
const LABEL: Record<string, string> = {
  "curator.contradictions": T("Contradicciones que propone el curador"), "verifier.refuted": T("Hechos que un verificador contradice"),
  correction: T("Correcciones"), duplicate: T("Posibles duplicados"), stale: T("Parecidas a algo que ya no es cierto"), new: T("Nuevas"),
};

/** The review queue by category (issue 299): decide a whole category after a look at its sample, and the tiers that approve one on their own. */
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
  return (
    <Stack gap="sm">
      <Notice tone="info">{t("Lo pendiente agrupado por lo que lo produjo. Mira la muestra de una categoría y apruébala o recházala entera; lo que tiene un secreto por revisar y las correcciones se quedan para decidirlas una a una. La precisión es la parte de sus propuestas que aprobaron los curadores; con la suficiente, un administrador puede hacer que la categoría se apruebe sola.")}</Notice>
      <MutationError error={decide.error ?? tier.error} />
      {decide.data && <Text size="sm">{t("Decididas: {{n}}.", { n: decide.data.done.length })}{decide.data.left ? ` ${t("Quedan {{n}} para otra vez.", { n: decide.data.left })}` : ""}</Text>}
      {!items.length && q.isSuccess && <EmptyState>{t("No hay nada pendiente.")}</EmptyState>}
      {items.map((c) => {
        const p = c.precision;
        const earned = p.decided >= c.auto.min && (p.precision ?? 0) >= c.auto.bar;
        return (<Panel key={c.category} withBorder p="sm"><Stack gap="xs">
          <Group justify="space-between" gap="xs">
            <Group gap="xs"><Text fw={600}>{t(LABEL[c.category] ?? c.category)}</Text><Pill size="sm" tone={c.pending ? "warn" : "neutral"}>{c.pending}</Pill>
              {c.auto.enabled && <Pill size="sm" tone="success">{t("Se aprueba sola")}</Pill>}</Group>
            {c.oldest && <Text size="xs" c="dimmed">{t("la más antigua: {{at}}", { at: fmt(c.oldest) })}</Text>}
          </Group>
          <Text size="xs" c="dimmed">{p.precision === null ? t("Ninguna decidida todavía por una persona.")
            : t("Precisión: {{pct}} ({{a}} aprobadas de {{d}} decididas por personas).", { pct: `${Math.round(p.precision * 100)} %`, a: p.approved, d: p.decided })}
            {c.flagged ? ` ${t("{{n}} con un secreto por revisar, que no se deciden en bloque.", { n: c.flagged })}` : ""}</Text>
          {c.sample.map((s) => <Text key={s.id} size="xs">#{s.id} · {s.name}{s.body ? ` — ${s.body}` : ""}{s.claims.map((cl, i) => <span key={i}> · {cl.subject} → {cl.relation} → {cl.value}{cl.facts.length ? ` (${cl.facts.join("; ")})` : ""}</span>)}</Text>)}
          {c.pending > 0 && <Group gap="xs">
            <Btn size="row" icon="check" onClick={() => setAsk({ cat: c, verb: "approve" })}>{t("Aprobar la categoría")}</Btn>
            <Btn size="row" kind="danger" onClick={() => setAsk({ cat: c, verb: "reject" })}>{t("Rechazar la categoría")}</Btn>
          </Group>}
          {isAdmin && <Check checked={c.auto.enabled} disabled={!c.auto.enabled && !earned} onChange={(e) => tier.mutate({ cat: c, enabled: e.currentTarget.checked })}
            label={t("Aprobar esta categoría automáticamente")}
            description={t("Solo con al menos {{min}} decisiones de personas y una precisión de {{bar}}. Si baja, vuelve a ser manual y avisa. Nunca aprueba lo que tiene un secreto por revisar.", { min: c.auto.min, bar: `${Math.round(c.auto.bar * 100)} %` })} />}
        </Stack></Panel>);
      })}
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)}
        title={ask?.verb === "approve" ? t("¿Aprobar toda la categoría?") : t("¿Rechazar toda la categoría?")}
        action={ask?.verb === "approve" ? t("Aprobar") : t("Rechazar")} tone={ask?.verb === "approve" ? "primary" : "danger"}
        onConfirm={() => (ask ? decide.mutateAsync(ask) : Promise.resolve())}>
        {ask && t("Se deciden sus {{n}} propuestas pendientes (hasta 200), las hayas visto o no, salvo las que tienen un secreto por revisar y las correcciones.", { n: ask.cat.pending })}
      </ConfirmDialog>
    </Stack>
  );
}
