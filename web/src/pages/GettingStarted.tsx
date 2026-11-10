import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fmt, get, send } from "../api";
import { Btn, MutationError, Section, Step, Steps, type IconName } from "../ui";
import { T } from "../i18n";
import { useState } from "react";

const OPEN_KEY = "mimirsynth.gettingStartedOpen";

export type Onboarding = { steps: { key: string; done: boolean; done_at: string | null }[]; done: number; total: number; dismissed: boolean; show: boolean };

type PageLink = { label: string; to: string; icon: IconName; admins?: boolean };
/** Each step of the checklist (issue 363): what it is, how to get there, the page where it is done and the wiki section that explains it,
 *  in each language of the wiki. The server says which are done (`GET /onboarding`), from what already happened in the person's brains. */
const STEPS: Record<string, { title: string; text: string; links: PageLink[]; wiki: { en: string; es: string } }> = {
  agent_recall: {
    title: T("Un agente hace su primer recall"),
    text: T("Crea un token de API y conecta tu agente por MCP o por la API: antes de responder, leerá lo que sabe el brain."),
    links: [{ label: T("Conectar un agente"), to: "/admin?seccion=connect", icon: "plus" }],
    wiki: { en: "Connect-agents", es: "Conectar-agentes" },
  },
  proposal_received: {
    title: T("Llega la primera propuesta de un agente"),
    text: T("Lo que un agente aprende mientras trabaja lo propone; queda en cuarentena hasta que alguien lo revisa."),
    links: [{ label: T("Propuestas"), to: "/propuestas", icon: "proposals" }],
    wiki: { en: "Proposals#from-an-agent", es: "Propuestas#desde-un-agente" },
  },
  proposal_approved: {
    title: T("Se aprueba la primera propuesta"),
    text: T("Un curador la aprueba en «Por revisar», o el decisor si encaja en el ámbito del brain. Solo entonces entra en la memoria."),
    links: [{ label: T("Por revisar"), to: "/propuestas?estado=pending&tipo=memory", icon: "proposals" }],
    wiki: { en: "Proposals#to-review", es: "Propuestas#por-revisar" },
  },
  document: {
    title: T("Añades el primer documento o carpeta"),
    text: T("Sube ficheros o añade una carpeta como fuente: el recall trae también sus pasajes."),
    links: [{ label: T("Conocimiento"), to: "/conocimiento", icon: "knowledge" }],
    wiki: { en: "Knowledge", es: "Conocimiento" },
  },
  ask: {
    title: T("Haces tu primera pregunta en Preguntar"),
    text: T("Mira lo que recibiría un agente para una pregunta, o pide una respuesta redactada con sus citas."),
    links: [{ label: T("Preguntar"), to: "/preguntar", icon: "ask" }],
    wiki: { en: "Ask", es: "Preguntar" },
  },
  second: {
    title: T("Conectas un segundo agente o invitas a otra persona"),
    text: T("Cada agente con su propio token; cada persona con su rol en el brain."),
    links: [{ label: T("Tokens de API"), to: "/cuenta?seccion=tokens", icon: "plus" }, { label: T("Miembros"), to: "/admin?seccion=members", icon: "admin", admins: true }],
    wiki: { en: "Brains-and-members#members", es: "Administrar-brains-y-miembros#miembros" },
  },
};

/** The getting-started checklist at the top of the home screen: what to do after the first recall, each step ticked by itself when it
 *  happens in any of the person's brains. It goes for good once every step is done or the person closes it. */
export default function GettingStarted({ role }: { role: string }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["onboarding"], queryFn: () => get<Onboarding>("onboarding"), staleTime: 30000,
    refetchInterval: (query) => (query.state.data?.show ? 30000 : false) });  // a step ticks while the screen is open
  const cfg = useQuery({ queryKey: ["config"], queryFn: () => get<{ links?: { wiki?: string } }>("config"), staleTime: Infinity });
  const close = useMutation({ mutationFn: () => send<Onboarding>("POST", "onboarding/dismiss"), onSuccess: (d) => qc.setQueryData(["onboarding"], d) });
  // Folded to one row by default: it sits under what waits for review, which is what the home screen is for (Product principle 1). Its
  // state is remembered in this browser.
  const [open, setOpen] = useState(() => { try { return localStorage.getItem(OPEN_KEY) === "1"; } catch { return false; } });
  const toggle = () => setOpen((o) => { try { localStorage.setItem(OPEN_KEY, o ? "0" : "1"); } catch { /* sin almacenamiento */ } return !o; });
  const d = q.data;
  if (!d?.show) return null;
  const wiki = cfg.data?.links?.wiki;
  const lang = i18n.language.startsWith("es") ? "es" : "en";
  const admin = ["admin", "owner"].includes(role);
  const next = d.steps.find((s) => !s.done && STEPS[s.key]);
  return (
    <Section title={t("Para empezar")} hint={open ? t("Cada paso se marca solo cuando ocurre en cualquiera de tus brains. La lista desaparece al completarla; si la cierras, no vuelve.") : undefined}
      actions={<Group gap={6}>
        <Btn size="row" icon={open ? "chevronDown" : "chevronRight"} aria-expanded={open} aria-controls="ms-getting-started" onClick={toggle}>{open ? t("Ocultar los pasos") : t("Ver los pasos")}</Btn>
        <Btn size="row" kind="ghost" icon="close" loading={close.isPending} onClick={() => close.mutate()}>{t("Cerrar la lista")}</Btn>
      </Group>}>
      <Stack gap="sm">
        <Text size="sm" c="dimmed">{t("{{done}} de {{total}} pasos hechos", { done: d.done, total: d.total })}{!open && next ? <> · {t("Siguiente:")} {t(STEPS[next.key].title)}</> : null}</Text>
        <MutationError error={close.error} />
        {open && <div id="ms-getting-started"><Steps label={t("Pasos para empezar")}>
          {d.steps.filter((s) => STEPS[s.key]).map((s) => {
            const step = STEPS[s.key];
            return (
              <Step key={s.key} title={t(step.title)} tone={s.done ? "success" : "neutral"}>
                {s.done ? <Text size="sm" c="dimmed">{t("Hecho · {{date}}", { date: fmt(s.done_at) })}</Text> : <>
                  <Text size="sm" className="ms-measure">{t(step.text)}</Text>
                  <Group gap={6} mt={6}>
                    {step.links.filter((l) => !l.admins || admin).map((l) => <Btn key={l.to} size="row" icon={l.icon} component={Link} to={l.to}>{t(l.label)}</Btn>)}
                    {wiki && <Btn size="row" icon="docs" component="a" href={`${wiki}/${step.wiki[lang]}`} target="_blank" rel="noopener noreferrer">{t("En la wiki")}</Btn>}
                  </Group>
                </>}
              </Step>
            );
          })}
        </Steps></div>}
      </Stack>
    </Section>
  );
}
