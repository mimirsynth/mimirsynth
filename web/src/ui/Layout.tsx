import { useTranslation } from "react-i18next";
import { ActionIcon as MActionIcon, Drawer as MDrawer, type DrawerProps, Modal as MModal, NavLink as MNavLink, Tooltip as MTooltip, Tabs as MTabs, type ModalProps, type TabsProps } from "@mantine/core";
import { useEffect, useState, type ComponentProps, type ReactNode } from "react";
import { NavLink as RouterNavLink } from "react-router-dom";
import { Btn } from "./Btn";
import { Icon, type IconName } from "./Icon";
import { MutationError, Notice, TextField } from "./Fields";

/** Pestañas de la aplicación: siempre subrayadas, también las de segundo nivel. */
function TabsRoot(props: Omit<TabsProps, "variant">) {
  return <MTabs {...props} variant="default" className={`ms-tabs${props.className ? ` ${props.className}` : ""}`} />;
}
export const Tabs = Object.assign(TabsRoot, { List: MTabs.List, Tab: MTabs.Tab, Panel: MTabs.Panel });

/** Diálogo de la aplicación: centrado, con título en la tipografía de títulos. */
export function Modal(props: ModalProps) {
  return <MModal centered {...props} className={`ms-modal${props.className ? ` ${props.className}` : ""}`} />;
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
  return (
    <MTooltip label={label} position="top">
      {to
        ? <RouterNavLink to={to} aria-label={label} className={({ isActive }) => `ms-roundbtn${isActive ? " active" : ""}`}>{children}</RouterNavLink>
        : <a href={href} target="_blank" rel="noopener noreferrer" aria-label={label} className="ms-roundbtn">{children}</a>}
    </MTooltip>
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
  return <MDrawer position="right" size="xl" {...rest} className={`ms-side${rest.className ? ` ${rest.className}` : ""}`}><div className="ms-drawer-body">{children}</div></MDrawer>;
}

/**
 * Confirmación de una acción que cambia o destruye datos. Un solo diálogo para toda la aplicación:
 * aviso de lo que pasa, el elemento afectado, y «Cancelar» + la acción con su verbo (Borrar / Quitar / Revocar).
 * `onConfirm` devuelve la promesa de la mutación (`mutateAsync`): el diálogo muestra su carga y su error y se cierra al acabar.
 * `requireText` pide escribir ese texto para habilitar la acción (borrados de grandes cosas).
 */
export function ConfirmDialog({ opened, onClose, title, warning, subject, action, tone = "danger", requireText, onConfirm, children }: {
  opened: boolean; onClose: () => void; title: string; warning?: ReactNode; subject?: ReactNode; action: string;
  tone?: "danger" | "primary"; requireText?: string; onConfirm: () => Promise<unknown>; children?: ReactNode;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [typed, setTyped] = useState("");
  useEffect(() => { if (opened) { setBusy(false); setError(null); setTyped(""); } }, [opened]);
  const run = async () => {
    setBusy(true); setError(null);
    try { await onConfirm(); onClose(); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  return (
    <Modal opened={opened} onClose={onClose} title={title}>
      <div className="ms-confirm">
        {warning && <Notice tone={tone === "danger" ? "warn" : "info"}>{warning}</Notice>}
        {subject && <div className="ms-confirm-subject">{subject}</div>}
        {children}
        {requireText && <TextField label={t("Escribe «{{requireText}}» para confirmar", { requireText: requireText })} value={typed} onChange={(e) => setTyped(e.currentTarget.value)} />}
        <MutationError error={error} />
        <div className="ms-confirm-actions">
          <Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn>
          <Btn kind={tone} icon={tone === "danger" ? "trash" : "check"} loading={busy} disabled={!!requireText && typed !== requireText} onClick={run}>{action}</Btn>
        </div>
      </div>
    </Modal>
  );
}

/** Cabecera de pantalla: título igual a la entrada del menú, una línea de ayuda y, a la derecha, acciones. */
export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="ms-pagehead">
      <div className="ms-pagehead-row"><h2 className="ms-pagehead-title">{title}</h2>{actions && <div className="ms-pagehead-actions">{actions}</div>}</div>
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
