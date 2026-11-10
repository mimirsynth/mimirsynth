import { useTranslation } from "react-i18next";
import { ActionIcon as MActionIcon, Drawer as MDrawer, type DrawerProps, Menu as MMenu, Modal as MModal, NavLink as MNavLink, Popover as MPopover, Tooltip as MTooltip, Tabs as MTabs, type ModalProps, type TabsProps } from "@mantine/core";
import { useEffect, useRef, useState, type ComponentProps, type ReactNode } from "react";
import { NavLink as RouterNavLink, useLocation } from "react-router-dom";
import { Btn } from "./Btn";
import { Icon, type IconName } from "./Icon";
import { MutationError, Notice, TextField } from "./Fields";

/** Pestañas de la aplicación: siempre subrayadas, también las de segundo nivel. */
function TabsRoot(props: Omit<TabsProps, "variant">) {
  return <MTabs {...props} variant="default" className={`ms-tabs${props.className ? ` ${props.className}` : ""}`} />;
}
/** A tab's view: the kit sets its top space and lays its parts out one under the other with the page's 12px rhythm (a padding asked for
 *  at the call site is ignored). */
function TabsPanel({ pt: _pt, className, ...rest }: ComponentProps<typeof MTabs.Panel>) {
  return <MTabs.Panel {...rest} className={`ms-tabpanel${className ? ` ${className}` : ""}`} />;
}
export const Tabs = Object.assign(TabsRoot, { List: MTabs.List, Tab: MTabs.Tab, Panel: TabsPanel });

/** Diálogo de la aplicación: centrado, con título en la tipografía de títulos. Its close button is named («Cerrar»): it is where the focus
 *  lands when a dialog opens, and a nameless one reads as just «button». */
export function Modal(props: ModalProps) {
  const { t } = useTranslation();
  return <MModal centered {...props} closeButtonProps={{ "aria-label": t("Cerrar"), ...props.closeButtonProps }}
    className={`ms-modal${props.className ? ` ${props.className}` : ""}`} />;
}

/** Entrada del menú lateral, con su icono. */
export function NavItem({ icon, ...rest }: { icon: IconName } & Omit<ComponentProps<typeof MNavLink>, "leftSection"> & Record<string, unknown>) {
  return <MNavLink {...(rest as any)} leftSection={<Icon name={icon} size={18} />} className={`ms-nav${(rest as any).className ? ` ${(rest as any).className}` : ""}`} />;
}

/** Botón de solo icono, con su ayuda emergente. */
export function IconButton({ icon, label, onClick, disabled }: { icon: IconName; label: string; onClick?: () => void; disabled?: boolean }) {
  return (
    <MTooltip label={label}>
      <MActionIcon variant="default" size={36} aria-label={label} className="ms-iconbtn" onClick={onClick} disabled={disabled}><Icon name={icon} /></MActionIcon>
    </MTooltip>
  );
}

/** Botón cuadrado de la barra lateral: enlaza a una página de la aplicación (`to`) o a una dirección externa (`href`, otra pestaña).
 *  `tour`: the guided tour points at it (`data-tour`). */
export function RoundLink({ label, to, href, tour, children }: { label: string; to?: string; href?: string; tour?: string; children: ReactNode }) {
  const { pathname } = useLocation();
  const isActive = !!to && (pathname === to || pathname.startsWith(`${to}/`));  // className como texto: Mantine 9 no admite la función de NavLink dentro de un Tooltip
  return (
    <MTooltip label={label} position="top">
      {to
        ? <RouterNavLink to={to} aria-label={label} data-tour={tour} className={`ms-roundbtn${isActive ? " active" : ""}`}>{children}</RouterNavLink>
        : <a href={href} target="_blank" rel="noopener noreferrer" aria-label={label} className="ms-roundbtn">{children}</a>}
    </MTooltip>
  );
}

/** Botón cuadrado de la barra lateral que ejecuta una acción (cerrar sesión): mismo aspecto que `RoundLink`. */
export function RoundButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <MTooltip label={label} position="top">
      <button type="button" aria-label={label} className="ms-roundbtn" onClick={onClick}>{children}</button>
    </MTooltip>
  );
}

/** Help menu of the sidebar: a square button like `RoundLink` that opens a menu of help entries, either links to another tab (`href`:
 *  documentation, source code, feedback) or actions (`onClick`: replay the guided tour). Mantine's menu: arrows move between entries,
 *  Escape closes it and gives the focus back to the button. `tour`: the guided tour points at it (`data-tour`). */
export function HelpMenu({ label, items, tour }: { label: string; tour?: string; items: { label: string; icon: IconName; href?: string; onClick?: () => void }[] }) {
  return (
    <MMenu position="top-start" withinPortal classNames={{ dropdown: "ms-menu" }}>
      <MTooltip label={label} position="top">{/* outside the target: inside it the tooltip swallows aria-haspopup and aria-expanded */}
        <MMenu.Target>
          <button type="button" aria-label={label} data-tour={tour} className="ms-roundbtn"><Icon name="help" /></button>
        </MMenu.Target>
      </MTooltip>
      <MMenu.Dropdown>
        {items.map((it) => it.href
          ? <MMenu.Item key={it.label} component="a" href={it.href} target="_blank" rel="noopener noreferrer" leftSection={<Icon name={it.icon} size={16} />}>{it.label}</MMenu.Item>
          : <MMenu.Item key={it.label} onClick={it.onClick} leftSection={<Icon name={it.icon} size={16} />}>{it.label}</MMenu.Item>)}
      </MMenu.Dropdown>
    </MMenu>
  );
}

/** Tarjeta de la persona en la barra lateral: su avatar y su nombre llevan a «Mi cuenta», y a su lado va el botón de cerrar sesión (children). */
export function UserCard({ to, label, avatar, name, sub, children }: { to: string; label: string; avatar: ReactNode; name: string; sub?: ReactNode; children?: ReactNode }) {
  const { pathname } = useLocation();
  const isActive = pathname === to || pathname.startsWith(`${to}/`);
  return (
    <div className="ms-usercard">
      <MTooltip label={label} position="top">
        <RouterNavLink to={to} aria-label={label} className={`ms-usercard-link${isActive ? " active" : ""}`}>{avatar}<span className="ms-usercard-text"><span className="ms-usercard-name">{name}</span>{sub && <span className="ms-usercard-sub">{sub}</span>}</span></RouterNavLink>
      </MTooltip>
      {children}
    </div>
  );
}

/** A screen (DESIGN.md, the Page Owns the Height Rule). By default a document: it grows with its content and the window scrolls. `fill`
 *  is for a screen that is one data surface (a table, the review queue, a canvas): it fills the window and its `FillArea` scrolls inside,
 *  so the title, tabs and filters stay in view. */
export function Page({ fill, children }: { fill?: boolean; children: ReactNode }) {
  useEffect(measureScrollbar, []);
  return <div className="ms-page" data-fill={fill ? "" : undefined}>{children}</div>;
}
let measured = false;
/** The width of a scrollbar in this browser, as `--ms-sb` (the Scroll Rule, theme.css): 0 where bars overlay the content. Measured once,
 *  on a probe with the same scrollbar as the data areas. */
function measureScrollbar() {
  if (measured) return;
  measured = true;
  const probe = document.createElement("div");
  probe.className = "ms-sb-probe";
  document.body.appendChild(probe);
  document.documentElement.style.setProperty("--ms-sb", `${probe.offsetWidth - probe.clientWidth}px`);
  probe.remove();
}
export function FillArea({ children }: { children: ReactNode }) {
  return <div className="ms-fill">{children}</div>;
}

/** Panel lateral deslizante para ver el detalle de un elemento; el contenido se desplaza por dentro. */
export function SidePanel({ children, ...rest }: Omit<DrawerProps, "position" | "size">) {
  const { t } = useTranslation();
  return <MDrawer position="right" size="xl" {...rest} closeButtonProps={{ "aria-label": t("Cerrar"), ...rest.closeButtonProps }} className={`ms-side${rest.className ? ` ${rest.className}` : ""}`}><div className="ms-drawer-body">{children}</div></MDrawer>;
}

/**
 * Confirmación de una acción que cambia o destruye datos. Un solo diálogo para toda la aplicación:
 * aviso de lo que pasa, el elemento afectado, y «Cancelar» + la acción con su verbo (Borrar / Quitar / Revocar).
 * `onConfirm` devuelve la promesa de la mutación (`mutateAsync`): el diálogo muestra su carga y su error y se cierra al acabar.
 * `requireText` pide escribir ese texto para habilitar la acción (borrados de grandes cosas).
 */
export function ConfirmDialog({ opened, onClose, title, warning, subject, action, tone = "danger", warn, alt, requireText, disabled, onConfirm, children }: {
  opened: boolean; onClose: () => void; title: string; warning?: ReactNode; subject?: ReactNode; action: string;
  tone?: "danger" | "primary"; requireText?: string; disabled?: boolean; onConfirm: () => Promise<unknown>; children?: ReactNode;
  /** The warning is a caution even though the action is not destructive: the action becomes the quiet override (no fill, first in the
   *  row, last when stacked on a phone), the safe choices carry the weight, and the focus starts on Cancel, so Enter never confirms it by
   *  reflex. */ warn?: boolean;
  /** A second way out, the opposite decision (reject instead of approve): a secondary button beside `action`, which keeps its tone and
   *  its place, so the main button is the same in every dialog. */ alt?: { label: string; icon?: IconName; onConfirm: () => Promise<unknown> };
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [typed, setTyped] = useState("");
  useEffect(() => { if (opened) { setBusy(false); setError(null); setTyped(""); } }, [opened]);
  const [running, setRunning] = useState<"action" | "alt" | null>(null);
  const run = async (which: "action" | "alt" = "action") => {
    setBusy(true); setRunning(which); setError(null);
    try { await (which === "alt" && alt ? alt.onConfirm() : onConfirm()); onClose(); } catch (e) { setError(e); } finally { setBusy(false); setRunning(null); }
  };
  const main = <Btn kind={warn ? "ghost" : tone} className={warn ? "ms-confirm-override" : undefined} icon={tone === "danger" ? "trash" : "check"} data-autofocus={!warn && tone === "primary" && !requireText ? true : undefined} loading={busy && running !== "alt"} disabled={disabled || (!!requireText && typed !== requireText) || (busy && running === "alt")} onClick={() => run()}>{action}</Btn>;
  return (
    <Modal opened={opened} onClose={onClose} title={title} size={alt ? "lg" : undefined}>{/* three choices fit on one row */}
      <div className="ms-confirm">
        {warning && <Notice tone={tone === "danger" || warn ? "warn" : "info"}>{warning}</Notice>}
        {subject && <div className="ms-confirm-subject">{subject}</div>}
        {children}
        {requireText && <TextField label={t("Escribe «{{requireText}}» para confirmar", { requireText: requireText })} value={typed} onChange={(e) => setTyped(e.currentTarget.value)} />}
        <MutationError error={error} />
        <div className="ms-confirm-actions" data-warn={warn ? "" : undefined}>
          {warn && main}{/* in the order they are seen on a wide screen, so Tab and a screen reader meet them as they are laid out */}
          <Btn kind={warn ? "secondary" : "ghost"} onClick={onClose} data-autofocus={warn ? true : undefined}>{t("Cancelar")}</Btn>
          {alt && <Btn kind="danger" icon={alt.icon} loading={busy && running === "alt"} disabled={busy && running !== "alt"} onClick={() => run("alt")}>{alt.label}</Btn>}
          {!warn && main}
        </div>
      </div>
    </Modal>
  );
}

/** Cabecera de pantalla: título igual a la entrada del menú y, a la derecha, acciones. `description`, what the screen is for, is not
 *  printed under the title, where it took two to six lines of every screen for something read once: it sits behind the «i» beside the
 *  title (`HelpTip`). */
export function PageHeader({ title, description, actions, meta }: { title: string; description?: ReactNode; actions?: ReactNode; meta?: ReactNode }) {
  useEffect(() => {  // the browser tab and its history say which page this is
    document.title = `${title} · MimirSynth`;
    return () => { document.title = "MimirSynth"; };
  }, [title]);
  // `meta`: small things that belong to the title (a type, other names), on its line and wrapping under it on a phone
  return (
    <header className="ms-pagehead">
      <div className="ms-pagehead-row"><div className="ms-pagehead-name"><h1 className="ms-pagehead-title">{title}</h1>
        {description && <HelpTip title={title}>{description}</HelpTip>}{meta && <div className="ms-pagehead-meta">{meta}</div>}</div>
        {actions && <div className="ms-pagehead-actions">{actions}</div>}</div>
    </header>
  );
}

/** The «i» beside a screen's title, a view's bar or a block's heading and, in a popover, what it is for. The one place where the interface
 *  explains itself: never as a paragraph on the page. A real button: a click, a tap, Enter or Space open it and Escape closes it, giving
 *  the focus back; resting the pointer on it opens it too, and it closes when the pointer leaves both. */
export function HelpTip({ title, children }: { title: string; children: ReactNode }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const pinned = useRef(false);  // opened by a click: the pointer leaving does not close it
  const timer = useRef<number | undefined>(undefined);
  const hover = (on: boolean) => {
    window.clearTimeout(timer.current);
    if (pinned.current) return;
    timer.current = window.setTimeout(() => setOpen(on), on ? 200 : 150);
  };
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const close = () => { pinned.current = false; setOpen(false); };
  return (
    <MPopover opened={open} onChange={(o) => { if (!o) close(); }} onDismiss={close} position="bottom-start" withinPortal closeOnEscape returnFocus
      trapFocus={false} width="auto" classNames={{ dropdown: "ms-pagehelp" }}>
      <MPopover.Target>
        <button type="button" className="ms-pagehelp-btn" aria-label={t("Qué es «{{title}}»", { title })} aria-expanded={open}
          onClick={() => { window.clearTimeout(timer.current); if (open && pinned.current) close(); else { pinned.current = true; setOpen(true); } }}
          onMouseEnter={() => hover(true)} onMouseLeave={() => hover(false)}>
          <Icon name="info" size={18} />
        </button>
      </MPopover.Target>
      <MPopover.Dropdown onMouseEnter={() => hover(true)} onMouseLeave={() => hover(false)}>
        <div className="ms-pagehead-help">{children}</div>
      </MPopover.Dropdown>
    </MPopover>
  );
}

/** Fila de tarjetas de cifras: se reparte en las columnas que caben (mínimo 170 px) y pasa a más filas sin romperse. */
export function StatGrid({ children }: { children: ReactNode }) {
  return <div className="ms-statgrid">{children}</div>;
}

/** Zona principal con un panel lateral de 300 px; por debajo de 1000 px el panel pasa debajo, a todo el ancho. */
export function SplitView({ main, aside }: { main: ReactNode; aside: ReactNode }) {
  return <div className="ms-split"><div className="ms-split-main">{main}</div><div className="ms-split-aside">{aside}</div></div>;
}
