import { useTranslation } from "react-i18next";
import { Text } from "@mantine/core";
import { useIsMutating, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { Btn, DataState, EmptyState, Page, PageHeader, StatCard, StatGrid, Tabs, useTabParam } from "../ui";
import Retype from "./Retype";
import VocabConflicts from "./VocabConflicts";
import VocabDuplicates from "./VocabDuplicates";
import VocabStale from "./VocabStale";

/** What waits for a person's decision in the brain (`null`: it could not be counted). `retype` only comes to administrators. */
export type Attention = { proposals: number | null; corrections: number | null; duplicates: number | null; conflicts: number | null;
  stale: number | null; retype?: number | null; refqueries: number | null };
type Dup = { key: string; members: { uuid: string; name: string; labels: string[]; degree: number }[] };
type Vocab = { ignored_duplicates?: string[]; duplicates: Dup[] };

const count = (n: number | null | undefined) => (n ? ` (${n})` : "");

/** One plain sentence on what a tool is for, who uses it and what happens when you act. */
export function TabIntro({ children }: { children: ReactNode }) {
  return <Text size="sm" c="dimmed" maw={820}>{children}</Text>;
}

/** Content quality (issue 164): the curation work on what the graph already holds, apart from the framework (Vocabulary). */
export default function Quality({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const isCurator = ["curator", "admin", "owner"].includes(role);
  const isAdmin = ["admin", "owner"].includes(role);
  const qc = useQueryClient();
  const [tab, setTab] = useTabParam("dup");
  const att = useQuery({ queryKey: ["attention", graph, "fresh"], enabled: isCurator, queryFn: () => get<Attention>(`brains/${graph}/attention`, { fresh: true }) });
  const vocab = useQuery({ queryKey: ["vocab", graph], enabled: isCurator, queryFn: () => get<Vocab>("vocabulary", { graph }) });
  // After any change made in a tab (a merge, a resolved contradiction, a confirmed fact…), the counters are read again, and the
  // home screen's block gets them too.
  const busy = useIsMutating();
  const was = useRef(0);
  useEffect(() => { if (was.current && !busy && isCurator) void att.refetch(); was.current = busy; }, [busy]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (att.data) qc.setQueryData(["attention", graph], att.data); }, [att.data, graph, qc]);
  const header = <PageHeader title={t("Calidad del contenido")} description={<>
    {t("El trabajo de curación sobre lo que ya hay en el grafo: entidades repetidas, hechos que se contradicen, entidades con un tipo dudoso y hechos que hay que volver a confirmar. Cambia cada día y lo hacen los curadores.")}{" "}
    {t("Lo que hace aparecer este trabajo (qué relación es de un solo valor, cuánto dura cada una) es el marco del brain, y está en")}{" "}
    <Btn kind="link" component={Link} to="/vocabulario">{t("Vocabulario")}</Btn>.</>} />;
  if (!isCurator) return <Page>{header}<EmptyState>{t("La calidad del contenido la revisa un curador o superior. Para leer la memoria, ve a Hechos.")}</EmptyState></Page>;
  const a = att.data;
  return (
    <Page>
      {header}
      <StatGrid>
        <StatCard label={t("Posibles duplicados")} value={a?.duplicates ?? "—"} hint={t("grupos por revisar")} />
        <StatCard label={t("Posibles contradicciones")} value={a?.conflicts ?? "—"} hint={t("grupos por decidir")} />
        {isAdmin && <StatCard label={t("Tipos dudosos")} value={a?.retype ?? "—"} hint={t("cambios de tipo por aprobar")} />}
        <StatCard label={t("Hechos a revisar")} value={a?.stale ?? "—"} hint={t("pasados de su vida útil")} />
      </StatGrid>
      <Text size="xs" c="dimmed">
        {t("Para leer y explorar la memoria:")} <Btn kind="link" component={Link} to="/hechos">{t("Hechos")}</Btn>.{" "}
        {t("Lo que dicen quienes usan el recall (sus valoraciones y las consultas de referencia) se mide en")}{" "}
        <Btn kind="link" component={Link} to="/preguntar?tab=calidad">{t("Preguntar → Calidad")}</Btn>.
      </Text>
      <Tabs value={tab} onChange={setTab} className="ms-tabs-fill">
        <Tabs.List>
          <Tabs.Tab value="dup">{t("Duplicados")}{count(a?.duplicates)}</Tabs.Tab>
          <Tabs.Tab value="conflicts">{t("Contradicciones")}{count(a?.conflicts)}</Tabs.Tab>
          {isAdmin && <Tabs.Tab value="corrector">{t("Tipos dudosos")}{count(a?.retype)}</Tabs.Tab>}
          <Tabs.Tab value="stale">{t("A revisar")}{count(a?.stale)}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="dup" pt="sm">
          {vocab.data ? <VocabDuplicates graph={graph} groups={vocab.data.duplicates} ignored={vocab.data.ignored_duplicates ?? []} isAdmin={isAdmin} />
            : <DataState query={vocab} />}
        </Tabs.Panel>
        <Tabs.Panel value="conflicts" pt="sm"><VocabConflicts graph={graph} role={role} /></Tabs.Panel>
        {isAdmin && <Tabs.Panel value="corrector" pt="sm"><Retype graph={graph} role={role} /></Tabs.Panel>}
        <Tabs.Panel value="stale" pt="sm"><VocabStale graph={graph} /></Tabs.Panel>
      </Tabs>
    </Page>
  );
}
