import { applyInstanceDefault, setLanguage, type Lang } from "./i18n";
import { T } from "./i18n";
import { useTranslation } from "react-i18next";
import { AppShell, Burger, Center, Group, Stack, Text, Title } from "@mantine/core";
import { Avatar, Btn, Icon, NavItem, Notice, Panel, Pill, RoundLink, SelectField, ThemeButton, EmptyState } from "./ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, NavLink as RouterLink, Route, Routes, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { ApiError, Brain, get, Me, send } from "./api";
import Overview from "./pages/Overview";
import Journal from "./pages/Journal";
import Facts from "./pages/Facts";
import GraphPage from "./pages/GraphPage";
import Query from "./pages/Query";
import Vocabulary from "./pages/Vocabulary";
import Admin from "./pages/Admin";
import Ask from "./pages/Ask";
import Logo from "./Logo";
import { AcceptScreen, AuthScreen, ChangePasswordScreen, TwoFactorSetupScreen } from "./pages/AuthPages";
import Proposals from "./pages/Proposals";
import Knowledge from "./pages/Knowledge";
import Account from "./pages/Account";
import Jobs from "./pages/Jobs";

const NAV = [
  { section: T("Memoria"), items: [
    { to: "/", icon: "overview" as const, label: T("Resumen") },
    { to: "/diario", icon: "journal" as const, label: T("Diario") },
    { to: "/hechos", icon: "facts" as const, label: T("Hechos") },
    { to: "/conocimiento", icon: "knowledge" as const, label: T("Conocimiento") },
  ] },
  { section: T("Explorar"), items: [
    { to: "/preguntar", icon: "ask" as const, label: T("Preguntar") },
    { to: "/grafo", icon: "graph" as const, label: T("Grafo") },
    { to: "/consulta", icon: "query" as const, label: T("Consulta") },
  ] },
  { section: T("Curación"), items: [
    { to: "/propuestas", icon: "proposals" as const, label: T("Propuestas") },
    { to: "/vocabulario", icon: "vocabulary" as const, label: T("Vocabulario") },
    { to: "/trabajos", icon: "jobs" as const, label: T("Trabajos") },
  ] },
];

export default function App() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const cfg = useQuery({ queryKey: ["config"], queryFn: () => get<{ name: string; auth_mode: string; version?: string; links?: { docs: string; repo: string; feedback: string } }>("config") });
  const me = useQuery({ queryKey: ["me"], queryFn: () => get<Me>("me"), retry: false });
  useEffect(() => { if (cfg.data) applyInstanceDefault((cfg.data as { default_language?: string }).default_language); }, [cfg.data]);
  useEffect(() => { if (me.data?.locale) setLanguage(me.data.locale as Lang); }, [me.data?.locale]);
  const brains = useQuery({ queryKey: ["brains"], enabled: !!me.data, queryFn: () => get<Brain[]>("brains") });
  const KEY = "mimirsynth.brain";
  const [brain, setBrainState] = useState(() => { try { return localStorage.getItem(KEY) ?? ""; } catch { return ""; } });
  const [menu, setMenu] = useState(false);
  const loc = useLocation();
  useEffect(() => setMenu(false), [loc.pathname]);
  const setBrain = (slug: string) => { setBrainState(slug); try { localStorage.setItem(KEY, slug); } catch { /* sin almacenamiento */ } };
  // Recuerda el brain activo entre recargas; si el guardado ya no existe (borrado, sin acceso), cae al primero de la lista.
  useEffect(() => {
    const list = brains.data;
    if (list?.length && !list.some((b) => b.slug === brain)) setBrain(list[0].slug);
  }, [brains.data, brain]);
  useEffect(() => { if (cfg.data) document.title = cfg.data.name; }, [cfg.data]);
  // Trabajos activos del brain: contador junto a «Trabajos»; se consulta más a menudo mientras haya alguno en marcha.
  const active = useQuery({ queryKey: ["jobs-summary", brain], enabled: !!me.data && !!brain, queryFn: () => get<{ active: number }>("jobs/summary", { graph: brain }),
    refetchInterval: (q) => ((q.state.data?.active ?? 0) > 0 ? 3000 : 20000) });
  const name = cfg.data?.name ?? "…";

  if (loc.pathname.startsWith("/acceso/")) return <AcceptScreen token={loc.pathname.slice("/acceso/".length)} name={name} />;
  if (me.error instanceof ApiError && me.error.status === 401) return <AuthScreen name={name} />;
  if (me.data?.must_change_password) return <ChangePasswordScreen name={name} />;
  if (me.data?.must_setup_2fa) return <TwoFactorSetupScreen name={name} />;
  if (me.error) {
    return (
      <Center className="ms-fullh"><Panel withBorder p="xl" w={420}><Stack>
        <Notice tone="danger" title={t("No se pudo cargar tu sesión")}>{(me.error as Error).message}</Notice>
        <Btn onClick={() => void me.refetch()} loading={me.isFetching}>{t("Reintentar")}</Btn>
      </Stack></Panel></Center>
    );
  }
  if (!me.data) return <Center className="ms-fullh"><EmptyState>{t("Cargando…")}</EmptyState></Center>;
  const cur = brains.data?.find((b) => b.slug === brain);

  return (
    <AppShell header={{ height: { base: 52, sm: 0 } }} navbar={{ width: 240, breakpoint: "sm", collapsed: { mobile: !menu } }} padding="md">
      <AppShell.Header hiddenFrom="sm" className="ms-mobilebar">
        <Burger opened={menu} onClick={() => setMenu((o) => !o)} size="sm" aria-label={menu ? t("Cerrar menú") : t("Abrir menú")} />
        <Logo size={26} name={name} />
      </AppShell.Header>
      <AppShell.Navbar p="xs" className="ms-navbar">
        <div className="ms-nav-top"><Logo size={30} name={name} /></div>
        <div className="ms-nav-scroll">
          {NAV.map((g) => (
            <div key={g.section} className="ms-nav-group">
              <div className="ms-nav-section">{t(g.section)}</div>
              {g.items.map((n) => <NavItem key={n.to} icon={n.icon} component={RouterLink} to={n.to} label={t(n.label)} end={n.to === "/"}
                rightSection={n.to === "/trabajos" && (active.data?.active ?? 0) > 0 ? <Pill size="xs" tone="warn" title={t("trabajos en cola o en marcha")}>{active.data!.active}</Pill> : undefined} />)}
            </div>))}
        </div>
        <div className="ms-nav-bottom">
          <div>
            <SelectField size="xs" aria-label={t("Brain activo")} value={brain} onChange={(v) => v && setBrain(v)} allowDeselect={false} data={(brains.data ?? []).map((b) => ({ value: b.slug, label: b.name }))} />
          </div>
          <div className="ms-iconrow">
            <RoundLink to="/cuenta" label={`Mi cuenta · ${me.data.name}${cur ? t(" · rol {{role}}", { role: cur.role }) : ""}`}><Avatar src={me.data.avatar} name={me.data.name} size={26} /></RoundLink>
            {cfg.data?.links?.docs && <RoundLink href={cfg.data.links.docs} label={t("Documentación")}><Icon name="docs" /></RoundLink>}
            {cfg.data?.links?.repo && <RoundLink href={cfg.data.links.repo} label={t("Código fuente")}><Icon name="repo" /></RoundLink>}
            {cfg.data?.links?.feedback && <RoundLink href={cfg.data.links.feedback} label={t("Comentarios y errores")}><Icon name="feedback" /></RoundLink>}
            <ThemeButton />
            <RoundLink to="/admin" label={t("Administración")}><Icon name="admin" /></RoundLink>
          </div>
          <div className="ms-version">{name} v{cfg.data?.version ?? ""}</div>
        </div>
      </AppShell.Navbar>
      <AppShell.Main>
        <Routes>
          <Route path="/admin" element={<Admin me={me.data} brain={brain} setBrain={setBrain} />} />
          <Route path="/cuenta" element={<Account />} />
          {brain ? (
            <>
              <Route path="/" element={<Overview graph={brain} />} />
              <Route path="/preguntar" element={<Ask graph={brain} role={cur?.role ?? "reader"} />} />
              <Route path="/propuestas" element={<Proposals graph={brain} role={cur?.role ?? "reader"} />} />
              <Route path="/diario" element={<Journal graph={brain} />} />
              <Route path="/trabajos" element={<Jobs graph={brain} role={cur?.role ?? "reader"} />} />
              <Route path="/conocimiento" element={<Knowledge graph={brain} role={cur?.role ?? "reader"} instanceAdmin={me.data.is_admin} />} />
              <Route path="/hechos" element={<Facts graph={brain} role={cur?.role ?? "reader"} />} />
              <Route path="/linea-temporal" element={<Navigate to="/hechos?vista=linea" replace />} />
              <Route path="/grafo" element={<GraphPage graph={brain} />} />
              <Route path="/tipos" element={<Navigate to="/vocabulario?tab=corrector" replace />} />
              <Route path="/vocabulario" element={<Vocabulary graph={brain} role={cur?.role ?? "reader"} />} />
              <Route path="/consulta" element={<Query graph={brain} />} />
            </>
          ) : <Route path="*" element={<Text c="dimmed">{t("No tienes acceso a ningún brain todavía. Pide a un administrador que te añada.")}</Text>} />}
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}
