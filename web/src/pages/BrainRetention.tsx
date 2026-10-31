import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Brain, fmt, get, send } from "../api";
import { Btn, MutationError, Notice, NumberField } from "../ui";

type Kinds = { rejected_days: number; jobs_days: number; ratings_days: number };
type Retention = { rejected_days: number | null; jobs_days: number | null; ratings_days: number | null; defaults: Kinds; effective: Kinds;
  last_run: { status: string; finished_at: string | null; result: { proposals: number; jobs: number } | null; error: string } | null };

/** Plazos de retención del brain: cuánto conserva el texto de las propuestas rechazadas y sus trabajos terminados. Vacío = el de la
 *  instancia; 0 = sin plazo. Una tarea diaria purga lo que lo supera. */
export default function BrainRetention({ brain }: { brain: Brain }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["retention", brain.slug];
  const q = useQuery({ queryKey: key, queryFn: () => get<Retention>(`brains/${brain.slug}/retention`) });
  const [rejected, setRejected] = useState<number | string>(""); const [jobsDays, setJobsDays] = useState<number | string>(""); const [ratingsDays, setRatingsDays] = useState<number | string>("");
  useEffect(() => { if (q.data) { setRejected(q.data.rejected_days ?? ""); setJobsDays(q.data.jobs_days ?? ""); setRatingsDays(q.data.ratings_days ?? ""); } }, [q.data]);
  const num = (v: number | string) => (v === "" || v === null ? null : Number(v));
  const save = useMutation({ mutationFn: () => send<Retention>("PUT", `brains/${brain.slug}/retention`, { rejected_days: num(rejected), jobs_days: num(jobsDays), ratings_days: num(ratingsDays) }),
    onSuccess: (r) => qc.setQueryData(key, r) });
  const run = useMutation({ mutationFn: () => send("POST", `brains/${brain.slug}/retention/run`), onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: key }), 1500) });
  const d = q.data;
  const inst = (n: number) => (n ? t("{{n}} días", { n }) : t("sin plazo"));
  const last = d?.last_run;
  return (
    <Stack gap="sm">
      <Notice tone="info">{t("Una tarea diaria purga lo que supera estos plazos y deja un resumen. Las propuestas rechazadas pierden su texto, pero conservan su estado, sus autores y sus fechas; los trabajos terminados se borran. Vacío usa el plazo de la instancia; 0 conserva para siempre. La auditoría no se purga.")}</Notice>
      <Group grow align="flex-start">
        <NumberField label={t("Texto de las propuestas rechazadas")} min={0} max={3650} suffix={` ${t("días")}`} value={rejected} onChange={setRejected}
          placeholder={d ? t("El de la instancia: {{v}}", { v: inst(d.defaults.rejected_days) }) : ""} />
        <NumberField label={t("Trabajos terminados")} min={0} max={3650} suffix={` ${t("días")}`} value={jobsDays} onChange={setJobsDays}
          placeholder={d ? t("El de la instancia: {{v}}", { v: inst(d.defaults.jobs_days) }) : ""} />
        <NumberField label={t("Valoraciones del recall")} min={0} max={3650} suffix={` ${t("días")}`} value={ratingsDays} onChange={setRatingsDays}
          placeholder={d ? t("El de la instancia: {{v}}", { v: inst(d.defaults.ratings_days) }) : ""} />
      </Group>
      {d && <Text size="xs" c="dimmed">{t("En vigor: propuestas rechazadas, {{p}}; trabajos terminados, {{j}}; valoraciones del recall, {{r}}.", { p: inst(d.effective.rejected_days), j: inst(d.effective.jobs_days), r: inst(d.effective.ratings_days) })}</Text>}
      <MutationError error={save.error ?? run.error} />
      <Group gap="xs">
        <Btn kind="primary" icon="save" loading={save.isPending} onClick={() => save.mutate()}>{t("Guardar")}</Btn>
        <Btn icon="play" disabled={!d || !(d.effective.rejected_days || d.effective.jobs_days || d.effective.ratings_days)} loading={run.isPending} onClick={() => run.mutate()}>{t("Purgar ahora")}</Btn>
      </Group>
      {last && <Text size="xs" c="dimmed">{last.status === "done" && last.result
        ? t("Última purga, {{d}}: {{p}} propuestas y {{j}} trabajos.", { d: fmt(last.finished_at!), p: last.result.proposals, j: last.result.jobs })
        : last.status === "failed" ? t("La última purga falló: {{e}}", { e: last.error }) : t("Purga en marcha…")}</Text>}
    </Stack>
  );
}
