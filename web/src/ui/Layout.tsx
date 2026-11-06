import { useTranslation } from "react-i18next";
import { ActionIcon as MActionIcon, Drawer as MDrawer, type DrawerProps, Modal as MModal, NavLink as MNavLink, Tooltip as MTooltip, Tabs as MTabs, type ModalProps, type TabsProps } from "@mantine/core";
import { useEffect, useState, type ComponentProps, type ReactNode } from "react";
import { NavLink as RouterNavLink, useLocation } from "react-router-dom";
import { Btn } from "./Btn";
import { Icon, type IconName } from "./Icon";
import { MutationError, Notice, TextField } from "./Fields";

/** Pestañas de la aplicación: siempre subrayadas, también las de segundo nivel. */
function TabsRoot(props: Omit<TabsProps, "variant">) {
  return <MTabs {...props} variant="default" className={`ms-tabs${props.className ? ` ${props.className}` : ""}`} />;
}
export const Tabs = Object.assign(TabsRoot, { List: MTabs.List, Tab: MTabs.Tab, Panel: MTabs.Panel });

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

/** Botón cuadrado de la barra lateral: enlaza a una página de la aplicación (`to`) o a una dirección externa (`href`, otra pestaña). */
export function RoundLink({ label, to, href, children }: { label: string; to?: string; href?: string; children: ReactNode }) {
  const { pathname } = useLocation();
  const isActive = !!to && (pathname === to || pathname.startsWith(`${to}/`));  // className como texto: Mantine 9 no admite la función de NavLink dentro de un Tooltip
  return (
    <MTooltip label={label} position="top">
      {to
        ? <RouterNavLink to={to} aria-label={label} className={`ms-roundbtn${isActive ? " active" : ""}`}>{children}</RouterNavLink>
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

/** Tarjeta de la persona en la barra lateral: su avatar y su nombre llevan a «Mi cuenta», y a su lado va el botón de cerrar sesión (children). */
export function UserCard({ to, label, avatar, name, children }: { to: string; label: string; avatar: ReactNode; name: string; children?: ReactNode }) {
  const { pathname } = useLocation();
  const isActive = pathname === to || pathname.startsWith(`${to}/`);
  return (
    <div className="ms-usercard">
      <MTooltip label={label} position="top">
        <RouterNavLink to={to} aria-label={label} className={`ms-usercard-link${isActive ? " active" : ""}`}>{avatar}<span className="ms-usercard-name">{name}</span></RouterNavLink>
      </MTooltip>
      {children}
    </div>
  );
}

/** Página que ocupa todo el alto disponible; su zona `FillArea` crece y desplaza por dentro. */
export function Page({ children }: { children: ReactNode }) {
  return <div className="ms-page">{children}</div>;
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
  /** The warning is a caution even though the action is not destructive. */ warn?: boolean;
  /** The way out the dialog recommends instead of `action`: it becomes the primary button, takes the focus (Enter runs it) and `action`
   *  turns secondary. */ alt?: { label: string; icon?: IconName; onConfirm: () => Promise<unknown> };
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
  return (
    <Modal opened={opened} onClose={onClose} title={title}>
      <div className="ms-confirm">
        {warning && <Notice tone={tone === "danger" || warn ? "warn" : "info"}>{warning}</Notice>}
        {subject && <div className="ms-confirm-subject">{subject}</div>}
        {children}
        {requireText && <TextField label={t("Escribe «{{requireText}}» para confirmar", { requireText: requireText })} value={typed} onChange={(e) => setTyped(e.currentTarget.value)} />}
        <MutationError error={error} />
        <div className="ms-confirm-actions">
          <Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn>
          <Btn kind={alt ? "secondary" : tone} icon={tone === "danger" ? "trash" : "check"} data-autofocus={!alt && tone === "primary" && !requireText ? true : undefined} loading={busy && running !== "alt"} disabled={disabled || (!!requireText && typed !== requireText) || (busy && running === "alt")} onClick={() => run()}>{action}</Btn>
          {alt && <Btn kind="primary" icon={alt.icon} loading={busy && running === "alt"} disabled={busy && running !== "alt"} onClick={() => run("alt")} data-autofocus>{alt.label}</Btn>}
        </div>
      </div>
    </Modal>
  );
}

/** Cabecera de pantalla: título igual a la entrada del menú, una línea de ayuda y, a la derecha, acciones. */
export function PageHeader({ title, description, actions, meta }: { title: string; description?: ReactNode; actions?: ReactNode; meta?: ReactNode }) {
  // `meta`: small things that belong to the title (a type, other names), on its line and wrapping under it on a phone
  return (
    <header className="ms-pagehead">
      <div className="ms-pagehead-row"><div className="ms-pagehead-name"><h1 className="ms-pagehead-title">{title}</h1>{meta && <div className="ms-pagehead-meta">{meta}</div>}</div>
        {actions && <div className="ms-pagehead-actions">{actions}</div>}</div>
      {description && <p className="ms-pagehead-help">{description}</p>}
    </header>
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
