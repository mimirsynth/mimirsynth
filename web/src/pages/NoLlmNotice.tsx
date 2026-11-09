import { useTranslation } from "react-i18next";
import { Group } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { get } from "../api";
import { Btn, Notice } from "../ui";

/** On the home screen, for as long as there is no LLM (the setup wizard lets it be skipped, issue 361): approved proposals wait without
 *  being ingested, and whoever curates should know why. It goes as soon as an engine is added. */
export default function NoLlmNotice({ role }: { role: string }) {
  const { t } = useTranslation();
  const st = useQuery({ queryKey: ["ai-status"], queryFn: () => get<{ llm?: { configured: boolean } }>("ai-status"), staleTime: 60000 });
  if (!["curator", "admin", "owner"].includes(role) || st.data?.llm?.configured !== false) return null;
  return (
    <Notice tone="warn" title={t("No hay ningún modelo LLM")}>
      {t("Las propuestas aprobadas esperan sin entrar en la memoria: hace falta un modelo de lenguaje que saque de ellas las entidades y los hechos. El recall sigue funcionando con lo que ya hay.")}
      {role !== "curator" && <Group mt={6}><Btn size="row" icon="admin" component={Link} to="/admin?seccion=llm">{t("Añadir un modelo LLM")}</Btn></Group>}
    </Notice>
  );
}
