import { useTranslation } from "react-i18next";
import { Group, Text } from "@mantine/core";
import { Link } from "react-router-dom";
import { Btn, Page, PageHeader, Panel, Step, Steps } from "../ui";

/** Primer arranque: el administrador de una instancia sin ningún brain aterriza aquí, no en «no tienes acceso». */
export default function FirstSteps({ docs }: { docs?: string }) {
  const { t } = useTranslation();
  return (
    <Page>
      <PageHeader title={t("Primeros pasos")} description={t("Todavía no hay ningún brain. Sin brain no hay memoria que ver: crea el primero para empezar.")}
        actions={<Btn kind="primary" icon="plus" component={Link} to="/admin?crear=brain">{t("Crea tu primer brain")}</Btn>} />
      <Panel maw={680}>
        <Steps>
          <Step title={t("Crea un brain")}>
            <Text size="sm">{t("Un brain es un dominio de conocimiento aislado, con su grafo, su ontología, sus miembros y sus tokens.")}</Text>
          </Step>
          <Step title={t("Configura los modelos de IA")}>
            <Text size="sm">{t("Añade un motor de embeddings y otro de LLM para extraer los hechos, y pulsa «Probar». Sin ellos las propuestas no se ingieren y el recall no devuelve nada.")}</Text>
            <Group gap={6} mt={6}>
              <Btn size="row" icon="admin" component={Link} to="/admin?seccion=llm">{t("Modelo LLM")}</Btn>
              <Btn size="row" icon="admin" component={Link} to="/admin?seccion=embedding">{t("Embeddings")}</Btn>
            </Group>
          </Step>
          <Step title={t("Crea un token de API")}>
            <Text size="sm">{t("Uno por agente, para el brain que vaya a usar y con el rol Colaborador: lo que proponga queda en cuarentena hasta que se aprueba.")}</Text>
            <Group gap={6} mt={6}><Btn size="row" icon="plus" component={Link} to="/cuenta?seccion=tokens">{t("Tokens de API")}</Btn></Group>
          </Step>
          <Step title={t("Conecta un agente")}>
            <Text size="sm">{t("Con el token, el agente lee la memoria (recall) y propone hechos nuevos por la API o por MCP; con Claude Code basta un «claude mcp add».")}</Text>
            {docs && <Group gap={6} mt={6}><Btn size="row" icon="docs" component="a" href={docs} target="_blank" rel="noopener noreferrer">{t("Documentación")}</Btn></Group>}
          </Step>
        </Steps>
      </Panel>
    </Page>
  );
}
