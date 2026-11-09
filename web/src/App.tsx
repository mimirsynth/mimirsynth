import { applyInstanceDefault, setLanguage, type Lang } from "./i18n";
import { T } from "./i18n";
import { useTranslation } from "react-i18next";
import { AppShell, Burger, Center, Group, Stack, Text, Title } from "@mantine/core";
import { Avatar, Btn, HelpMenu, Icon, NavItem, Notice, Panel, Pill, RoundButton, RoundLink, SelectField, UserCard, ThemeButton, EmptyState, ErrorBoundary, shouldAutoStart } from "./ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, NavLink as RouterLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useMediaQuery } from "@mantine/hooks";
import { ApiError, Brain, get, Me, send } from "./api";
import Logo from "./Logo";
import { AcceptScreen, AuthScreen, ChangePasswordScreen, TwoFactorSetupScreen } from "./pages/AuthPages";
import type { Summary } from "./pages/Notifications";
import GuidedTour from "./pages/GuidedTour";
// Each screen is its own chunk, loaded the first time it is opened: the first visit downloads the shell and one screen, not all fifty.
const Overview = lazy(() => import("./pages/Overview"));
const Journal = lazy(() => import("./pages/Journal"));
const Facts = lazy(() => import("./pages/Facts"));
const GraphPage = lazy(() => import("./pages/GraphPage"));
const Query = lazy(() => import("./pages/Query"));
const Vocabulary = lazy(() => import("./pages/Vocabulary"));
const Admin = lazy(() => import("./pages/Admin"));
const Ask = lazy(() => import("./pages/Ask"));
const Proposals = lazy(() => import("./pages/Proposals"));
const Knowledge = lazy(() => import("./pages/Knowledge"));
const Account = lazy(() => import("./pages/Account"));
const Jobs = lazy(() => import("./pages/Jobs"));
const FirstSteps = lazy(() => import("./pages/FirstSteps"));
const SetupWizard = lazy(() => import("./pages/SetupWizard"));
const EntityPage = lazy(() => import("./pages/EntityPage"));
const Quality = lazy(() => import("./pages/Quality"));
const Notifications = lazy(() => import("./pages/Notifications"));

const NAV = [
  { section: T("Memoria"), items: [
    { to: "/", icon: "overview" as const, label: T("Resumen") },
    { to: "/diario", icon: "journal" as const, label: T("Diario") },
    { to: "/hechos", icon: "facts" as const, label: T("Hechos") },
    { to: "/conocimiento", icon: "knowledge" as const, label: T("Conocimiento") },
  ] },
  { section: T("Explorar"), items: [
    { to: "/preguntar", icon: "ask" as const, label: T("Preguntar"), tour: "ask" },
    { to: "/grafo", icon: "graph" as const, label: T("Grafo"), tour: "graph" },
    { to: "/consulta", icon: "query" as const, label: T("Consulta") },
  ] },
  { section: T("Curación"), items: [
    { to: "/propuestas", icon: "proposals" as const, label: T("Propuestas"), tour: "proposals" },
    { to: "/calidad", icon: "quality" as const, label: T("Calidad del contenido"), curators: true },
    { to: "/vocabulario", icon: "vocabulary" as const, label: T("Vocabulario") },
    { to: "/trabajos", icon: "jobs" as const, label: T("Trabajos") },
  ] },
];

/** What went wrong when the session could not be loaded, said so that someone can act on it: the browser could not reach the server,
 *  the proxy reached it but MimirSynth did not answer (starting, updating or down), or the server explained the problem itself.
 *  The HTTP status stays underneath, small, for whoever administers the instance. */
const GENERIC_STATUS = new Set(["", "Bad Gateway", "Service Unavailable", "Gateway Timeout", "Internal Server Error"]);
function sessionProblem(error: unknown, t: (k: string) => string) {
  if (!(error instanceof ApiError)) return <Text size="sm">{t("No se puede contactar con el servidor de MimirSynth. Comprueba la conexión y vuelve a intentarlo.")}</Text>;
  const gateway = [502, 503, 504].includes(error.status) && GENERIC_STATUS.has(error.message);
  const text = gateway ? t("El servidor de MimirSynth no responde: puede estar arrancando o actualizándose. Vuelve a intentarlo en un momento y, si sigue igual, avisa a quien administra la instancia.")
    : GENERIC_STATUS.has(error.message) ? t("El servidor de MimirSynth ha fallado al cargar tu sesión. Vuelve a intentarlo y, si sigue igual, avisa a quien administra la instancia.")
    : error.message;
  return <><Text size="sm">{text}</Text><Text size="xs" c="dimmed" className="ms-data">{`HTTP ${error.status}`}</Text></>;
}

export default function App() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const cfg = useQuery({ queryKey: ["config"], queryFn: () => get<{ name: string; auth_mode: string; version?: string; stage?: string; links?: { docs: string; repo: string; feedback: string } }>("config") });
  const me = useQuery({ queryKey: ["me"], queryFn: () => get<Me>("me"), retry: false });
  const logout = useMutation({ mutationFn: () => send("POST", "auth/logout"), onSuccess: () => { qc.clear(); window.location.href = "/"; } });
  useEffect(() => { if (cfg.data) applyInstanceDefault((cfg.data as { default_language?: string }).default_language); }, [cfg.data]);
  useEffect(() => { if (me.data?.locale) setLanguage(me.data.locale as Lang); }, [me.data?.locale]);
  const brains = useQuery({ queryKey: ["brains"], enabled: !!me.data, queryFn: () => get<Brain[]>("brains") });
  const KEY = "mimirsynth.brain";
  const [brain, setBrainState] = useState(() => { try { return localStorage.getItem(KEY) ?? ""; } catch { return ""; } });
  const [menu, setMenu] = useState(false);
  const loc = useLocation();
  const navigate = useNavigate();
  useEffect(() => setMenu(false), [loc.pathname]);
  // The setup wizard (issue 361) opens by itself, once per visit, for an administrator of an instance not yet set up; leaving it is allowed,
  // and it resumes where it stopped the next time.
  const wizardOpened = useRef(false);
  const onWizard = loc.pathname === "/configuracion";
  useEffect(() => {
    if (me.data?.setup_pending && !wizardOpened.current && !onWizard && !loc.pathname.startsWith("/acceso/")) { wizardOpened.current = true; navigate("/configuracion"); }
    if (onWizard) wizardOpened.current = true;
  }, [me.data?.setup_pending, onWizard]);  // eslint-disable-line react-hooks/exhaustive-deps
  const setBrain = (slug: string) => { setBrainState(slug); try { localStorage.setItem(KEY, slug); } catch { /* sin almacenamiento */ } };
  // A link with ?brain=<slug> (the periodic summary) opens that brain if the person has it; the parameter then goes away.
  useEffect(() => {
    const q = new URLSearchParams(loc.search);
    const want = q.get("brain");
    if (!want || !brains.data) return;
    if (brains.data.some((b) => b.slug === want)) setBrain(want);
    q.delete("brain");
    navigate({ pathname: loc.pathname, search: q.toString() ? `?${q}` : "" }, { replace: true });
  }, [brains.data, loc.search]);  // eslint-disable-line react-hooks/exhaustive-deps
  // Recuerda el brain activo entre recargas; si el guardado ya no existe (borrado, sin acceso), cae al primero de la lista.
  useEffect(() => {
    const list = brains.data;
    if (list?.length && !list.some((b) => b.slug === brain)) setBrain(list[0].slug);
  }, [brains.data, brain]);
  useEffect(() => { if (cfg.data) document.title = cfg.data.name; }, [cfg.data]);
  // Trabajos activos del brain: contador junto a «Trabajos»; se consulta más a menudo mientras haya alguno en marcha.
  const active = useQuery({ queryKey: ["jobs-summary", brain], enabled: !!me.data && !!brain, queryFn: () => get<{ active: number }>("jobs/summary", { graph: brain }),
    refetchInterval: (q) => ((q.state.data?.active ?? 0) > 0 ? 3000 : 20000) });
  const bell = useQuery({ queryKey: ["notifications-summary"], enabled: !!me.data, queryFn: () => get<Summary>("notifications/summary"), refetchInterval: 30000 });
  const name = cfg.data?.name ?? "…";
  // The guided tour (issue 364) starts on its own once, for whoever has not finished or skipped it, as soon as there is a brain to show; the
  // help menu replays it. On a phone its steps point into the navigation, so the menu opens for them and closes at the end.
  const narrow = useMediaQuery("(max-width: 48em)") ?? false;
  const [tour, setTour] = useState(false);
  const tourStarted = useRef(false);
  const hasBrain = !!brains.data?.some((b) => b.slug === brain);
  useEffect(() => {
    if (!onWizard && !me.data?.setup_pending && shouldAutoStart({ tourSeen: me.data?.tour_seen, hasBrain, startedHere: tourStarted.current })) { tourStarted.current = true; setTour(true); }
  }, [me.data?.tour_seen, hasBrain, onWizard, me.data?.setup_pending]);  // eslint-disable-line react-hooks/exhaustive-deps
  const tourSeen = useMutation({ mutationFn: () => send("POST", "me/tour", { seen: true }), onSuccess: () => qc.setQueryData<Me>(["me"], (m) => (m ? { ...m, tour_seen: true } : m)) });
  const closeTour = (persist: boolean) => { setTour(false); if (narrow) setMenu(false); if (persist) tourSeen.mutate(); };
  const replayTour = () => { tourStarted.current = true; setTour(true); };

  if (loc.pathname.startsWith("/acceso/")) return <AcceptScreen token={loc.pathname.slice("/acceso/".length)} name={name} />;
  if (me.error instanceof ApiError && me.error.status === 401) return <AuthScreen name={name} />;
  if (me.data?.must_change_password) return <ChangePasswordScreen name={name} />;
  if (me.data?.must_setup_2fa) return <TwoFactorSetupScreen name={name} />;
  if (me.error) {
    return (
      <Center component="main" className="ms-fullh"><Panel withBorder p="xl" className="ms-authcard"><Stack>
        <h1 className="ms-sr">{`${cfg.data?.name ?? "MimirSynth"} · ${t("No se pudo cargar tu sesión")}`}</h1>
        <Notice tone="danger" title={t("No se pudo cargar tu sesión")}>
          <Stack gap={4}>{sessionProblem(me.error, t)}</Stack>
        </Notice>
        <Btn onClick={() => void me.refetch()} loading={me.isFetching}>{t("Reintentar")}</Btn>
      </Stack></Panel></Center>
    );
  }
  if (!me.data) return <Center component="main" className="ms-fullh"><EmptyState>{t("Cargando…")}</EmptyState></Center>;
  const cur = brains.data?.find((b) => b.slug === brain);

  return (
    <AppShell header={{ height: { base: 52, sm: 0 } }} navbar={{ width: 240, breakpoint: "sm", collapsed: { mobile: !menu } }} padding="md">
      <AppShell.Header hiddenFrom="sm" className="ms-mobilebar">
        <Burger opened={menu} onClick={() => setMenu((o) => !o)} size="sm" aria-label={menu ? t("Cerrar menú") : t("Abrir menú")} />
        <Logo size={26} name={name} />
      </AppShell.Header>
      <AppShell.Navbar p="xs" className="ms-navbar">
        <div className="ms-nav-top"><Logo size={30} name={name} /></div>
        <div className="ms-nav-scroll" data-tour="nav">
          {NAV.map((g) => (
            <div key={g.section} className="ms-nav-group">
              <div className="ms-nav-section">{t(g.section)}</div>
              {g.items.filter((n) => !("curators" in n) || ["curator", "admin", "owner"].includes(cur?.role ?? "")).map((n) => <NavItem key={n.to} icon={n.icon} component={RouterLink} to={n.to} label={t(n.label)} end={n.to === "/"} data-tour={"tour" in n ? n.tour : undefined}
                active={n.to === "/hechos" && loc.pathname.startsWith("/entidad/") ? true : undefined}  // an entity page belongs to Facts
                rightSection={n.to === "/trabajos" && (active.data?.active ?? 0) > 0 ? <Pill size="xs" tone="warn" title={t("trabajos en cola o en marcha")}>{active.data!.active}</Pill> : undefined} />)}
            </div>))}
        </div>
        <div className="ms-nav-bottom">
          <NavItem icon="bell" component={RouterLink} to="/notificaciones" label={t("Notificaciones")}
            rightSection={bell.data?.unread ? <Pill size="xs" tone={bell.data.worst === "critical" ? "danger" : "warn"} title={t("avisos sin leer")}>{bell.data.unread}</Pill>
              : bell.data?.open ? <Pill size="xs" title={t("problemas abiertos")}>{bell.data.open}</Pill> : undefined} />
          <div data-tour="brain">
            <SelectField size="xs" aria-label={t("Brain activo")} value={brain} onChange={(v) => v && setBrain(v)} allowDeselect={false} data={(brains.data ?? []).map((b) => ({ value: b.slug, label: b.name }))} />
          </div>
          <UserCard to="/cuenta" label={`Mi cuenta · ${me.data.name}${cur ? t(" · rol {{role}}", { role: cur.role }) : ""}`} avatar={<Avatar src={me.data.avatar} name={me.data.name} size={26} />} name={me.data.name}>
            {me.data.auth_mode !== "off" && <RoundButton label={t("Cerrar sesión")} onClick={() => logout.mutate()}><Icon name="logout" /></RoundButton>}
          </UserCard>
          <div className="ms-iconrow">
            <HelpMenu label={t("Ayuda")} tour="help" items={[
              { label: t("Ver el recorrido guiado"), icon: "tour", onClick: replayTour },
              ...(cfg.data?.links?.docs ? [{ label: t("Documentación"), icon: "docs" as const, href: cfg.data.links.docs }] : []),
              ...(cfg.data?.links?.repo ? [{ label: t("Código fuente"), icon: "repo" as const, href: cfg.data.links.repo }] : []),
              ...(cfg.data?.links?.feedback ? [{ label: t("Comentarios y errores"), icon: "feedback" as const, href: cfg.data.links.feedback }] : []),
            ]} />
            <ThemeButton />
            <RoundLink to="/admin" label={t("Administración")} tour="admin"><Icon name="admin" /></RoundLink>
          </div>
          <div className="ms-version">{name} v{cfg.data?.version ?? ""}
            {cfg.data?.stage === "beta" && <> <Pill size="xs" tone="warn" title={t("Hasta la versión 1.0, la API y el esquema pueden cambiar entre versiones menores.")}>{t("Beta pública")}</Pill></>}</div>
        </div>
      </AppShell.Navbar>
      <AppShell.Main>
        <ErrorBoundary resetKey={`${loc.pathname}|${brain}`}>
        <Suspense fallback={<EmptyState>{t("Cargando…")}</EmptyState>}>
        <Routes>
          <Route path="/admin" element={<Admin me={me.data} brain={brain} setBrain={setBrain} />} />
          <Route path="/cuenta" element={<Account />} />
          <Route path="/notificaciones" element={<Notifications />} />
          {me.data.is_admin && <Route path="/configuracion" element={<SetupWizard />} />}
          {brain ? (
            <>
              <Route path="/" element={<Overview graph={brain} role={cur?.role ?? "reader"} />} />
              <Route path="/preguntar" element={<Ask graph={brain} role={cur?.role ?? "reader"} />} />
              <Route path="/propuestas" element={<Proposals graph={brain} role={cur?.role ?? "reader"} />} />
              <Route path="/diario" element={<Journal graph={brain} />} />
              <Route path="/trabajos" element={<Jobs graph={brain} role={cur?.role ?? "reader"} />} />
              <Route path="/conocimiento" element={<Knowledge graph={brain} role={cur?.role ?? "reader"} instanceAdmin={me.data.is_admin} />} />
              <Route path="/hechos" element={<Facts graph={brain} role={cur?.role ?? "reader"} />} />
              <Route path="/linea-temporal" element={<Navigate to="/hechos?vista=linea" replace />} />
              <Route path="/grafo" element={<GraphPage graph={brain} />} />
              <Route path="/tipos" element={<Navigate to="/calidad?tab=corrector" replace />} />
              <Route path="/calidad" element={<Quality graph={brain} role={cur?.role ?? "reader"} />} />
              <Route path="/vocabulario" element={<Vocabulary graph={brain} role={cur?.role ?? "reader"} />} />
              <Route path="/consulta" element={<Query graph={brain} />} />
              <Route path="/entidad/:uuid" element={<EntityPage graph={brain} role={cur?.role ?? "reader"} />} />
            </>
          ) : <Route path="*" element={brains.isPending ? <EmptyState>{t("Cargando…")}</EmptyState>
            // El administrador ve todos los brains: si la lista está vacía es que no existe ninguno, y nadie más puede crearlo.
            : me.data.is_admin && brains.data?.length === 0 ? (me.data.setup_pending ? <Navigate to="/configuracion" replace /> : <FirstSteps docs={cfg.data?.links?.docs} />)
            : <Text c="dimmed">{t("No tienes acceso a ningún brain todavía. Pide a un administrador que te añada.")}</Text>} />}
        </Routes>
        </Suspense>
        </ErrorBoundary>
      </AppShell.Main>
      <GuidedTour opened={tour && !!cur} onClose={closeTour} onStep={(s) => { if (narrow) setMenu(!!s.target); }} />
    </AppShell>
  );
}
