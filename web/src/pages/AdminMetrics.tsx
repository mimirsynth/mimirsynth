import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, CodeBlock, ConfirmDialog, DataState, MutationError, Notice, Pill, SecretReveal, SettingsBody, SettingsGroup, SettingsRow } from "../ui";

type State = { enabled: boolean; prefix: string; created_at: string | null; created_by: string | null; last_read_at: string | null; url: string };

/** Prometheus metrics at /metrics: the token that reads them is generated here, shown once, and can be replaced or revoked. */
export default function AdminMetrics() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-metrics"], queryFn: () => get<State>("admin/metrics") });
  const [shown, setShown] = useState("");
  const [ask, setAsk] = useState<"rotate" | "revoke" | null>(null);
  const done = (d: State) => qc.setQueryData(["admin-metrics"], d);
  const create = useMutation({ mutationFn: () => send<State & { token: string }>("POST", "admin/metrics/token"), onSuccess: (d) => { setShown(d.token); done(d); } });
  const revoke = useMutation({ mutationFn: () => send<State>("DELETE", "admin/metrics/token"), onSuccess: done });
  return (
    <SettingsGroup title={t("Métricas")} description={t("Métricas de Prometheus en /metrics: tiempo del recall, trabajos, propuestas, documentos y llamadas a los motores de IA. Solo responden a quien presenta el token que se genera aquí.")}>
      <DataState query={q}>
        {(d) => <>
          <SettingsRow label={t("Estado")}>
            {d.enabled ? <Pill tone="success">{t("activadas")}</Pill> : <Pill>{t("desactivadas: /metrics responde 404")}</Pill>}
          </SettingsRow>
          {d.enabled && <>
            <SettingsRow label={t("Token")}><Text size="sm" className="ms-data">{d.prefix}…</Text></SettingsRow>
            <SettingsRow label={t("Creado")}>{fmt(d.created_at)}{d.created_by ? ` · ${d.created_by}` : ""}</SettingsRow>
            <SettingsRow label={t("Última lectura")} help={t("Desde el último arranque de la aplicación.")}>{d.last_read_at ? fmt(d.last_read_at) : t("ninguna todavía")}</SettingsRow>
          </>}
          <SettingsBody><Stack gap="sm">
            <MutationError error={create.error ?? revoke.error} />
            <Group gap="xs">
              {d.enabled
                ? <><Btn size="row" icon="refresh" onClick={() => setAsk("rotate")}>{t("Generar otro token")}</Btn>
                  <Btn size="row" kind="danger" icon="trash" onClick={() => setAsk("revoke")}>{t("Revocar y desactivar")}</Btn></>
                : <Btn size="row" kind="primary" icon="plus" loading={create.isPending} onClick={() => create.mutate()}>{t("Activar y generar token")}</Btn>}
            </Group>
            {d.enabled && <>
              <Text size="sm">{t("Configuración de Prometheus (guarda el token, solo, en el fichero de credentials_file):")}</Text>
              <CodeBlock copy>{`scrape_configs:\n  - job_name: mimirsynth\n    scrape_interval: 60s\n    metrics_path: /metrics\n    scheme: ${d.url.startsWith("https://") ? "https" : "http"}\n    authorization:\n      credentials_file: /etc/prometheus/mimirsynth.token\n    static_configs:\n      - targets: ["${hostOf(d.url)}"]`}</CodeBlock>
              {!d.url.startsWith("http") && <Notice tone="info">{t("Sin URL pública configurada: pon en targets la dirección por la que Prometheus llega a la aplicación.")}</Notice>}
            </>}
          </Stack></SettingsBody>
        </>}
      </DataState>
      <SecretReveal value={shown} title={t("Token de las métricas")} onClose={() => setShown("")} />
      <ConfirmDialog opened={ask === "rotate"} onClose={() => setAsk(null)} title={t("Generar otro token")} action={t("Generar")} tone="primary"
        warning={t("El token actual deja de valer al momento: actualiza Prometheus con el nuevo.")} onConfirm={() => create.mutateAsync()} />
      <ConfirmDialog opened={ask === "revoke"} onClose={() => setAsk(null)} title={t("Revocar y desactivar")} action={t("Revocar")}
        warning={t("/metrics volverá a responder 404 y Prometheus dejará de recibir datos.")} onConfirm={() => revoke.mutateAsync()} />
    </SettingsGroup>
  );
}

function hostOf(url: string): string {
  try { return new URL(url).host || "mimirsynth:8000"; } catch { return "mimirsynth:8000"; }
}
