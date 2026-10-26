import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, DataState, EmptyState, FillArea, ListCard, Page, PageHeader, Pill, Segments, Tone } from "../ui";

export type Summary = { unread: number; open: number; worst: "critical" | "warning" | "info" | null };
type Item = { id: number; ts: string; last_at: string; event: string; severity: string; title: string; body: string; count: number; brain: string | null; resolved_at: string | null; unread: boolean };

export const SEVERITY: Record<string, { label: string; tone: Tone | undefined }> = {
  critical: { label: T("Crítico"), tone: "danger" }, warning: { label: T("Aviso"), tone: "warn" }, info: { label: T("Información"), tone: undefined },
};

/** Campana: avisos del sistema para esta persona (administradores: toda la instancia; curadores: los de sus brains). Los problemas se agrupan y se marcan al resolverse. */
export default function Notifications() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [view, setView] = useState("all");
  const q = useQuery({ queryKey: ["notifications", view], queryFn: () => get<{ total: number; items: Item[] }>("notifications", { unread: view === "unread" ? "true" : undefined, limit: "100" }), refetchInterval: 30000 });
  const sum = useQuery({ queryKey: ["notifications-summary"], queryFn: () => get<Summary>("notifications/summary") });
  const read = useMutation({ mutationFn: () => send("POST", "notifications/read"), onSuccess: () => { qc.invalidateQueries({ queryKey: ["notifications"] }); qc.invalidateQueries({ queryKey: ["notifications-summary"] }); } });
  return (
    <Page>
      <PageHeader title={t("Notificaciones")} description={t("Problemas y avisos del sistema: modelos que no responden, ingestas fallidas, fuentes con error, versiones nuevas. Un problema que se repite cuenta una sola vez y se marca cuando se resuelve.")}
        actions={<Btn size="row" icon="check" disabled={!sum.data?.unread} loading={read.isPending} onClick={() => read.mutate()}>{t("Marcar todo como leído")}</Btn>} />
      <FillArea><Stack gap="xs">
        <Segments value={view} onChange={setView} data={[{ value: "all", label: t("Todas") }, { value: "unread", label: t("Sin leer"), count: sum.data?.unread }]} />
        <DataState query={q}>{() => (
          q.data?.items.length ? q.data.items.map((n) => (
            <ListCard key={n.id} invalid={!!n.resolved_at}
              title={<Group gap={8} wrap="nowrap">{n.unread && <Pill size="xs" tone="alt">{t("nuevo")}</Pill>}<Text fw={600} size="sm">{n.title}</Text></Group>}
              aside={fmt(n.last_at)}
              tags={<><Pill size="xs" tone={SEVERITY[n.severity]?.tone}>{t(SEVERITY[n.severity]?.label ?? n.severity)}</Pill>
                {n.resolved_at ? <Pill size="xs" tone="success">{t("resuelto")} {fmt(n.resolved_at)}</Pill> : <Pill size="xs" tone="warn">{t("abierto")}</Pill>}
                {n.brain && <Pill size="xs">{n.brain}</Pill>}{n.count > 1 && <Pill size="xs">{t("{{n}} veces", { n: n.count })}</Pill>}</>}>
              {n.body}
            </ListCard>)) : <EmptyState>{view === "unread" ? t("No tienes avisos sin leer.") : t("Todo en orden: no hay avisos.")}</EmptyState>
        )}</DataState>
      </Stack></FillArea>
    </Page>
  );
}
