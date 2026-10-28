import { Button, type ButtonProps } from "@mantine/core";
import type { ComponentPropsWithoutRef, CSSProperties } from "react";
import { Icon, type IconName } from "./Icon";

export type BtnKind = "primary" | "secondary" | "ghost" | "danger" | "link";
type Props = Omit<ButtonProps, "variant" | "color" | "size"> & ComponentPropsWithoutRef<"button"> & { kind?: BtnKind; size?: "row"; component?: any; href?: string; to?: string; target?: string; icon?: IconName };

/** Botón de la aplicación. Toda acción es un botón y por defecto es SECUNDARIO (borde):
 *  - `kind="primary"` (hidromiel): la acción principal de una zona (el envío de un modal, «Buscar»…). Como mucho una por zona.
 *  - `kind="ghost"`: acción discreta sin borde (Cancelar, quitar filtros).
 *  - `kind="danger"`: destructiva (borde rojo).
 *  - `kind="link"`: solo texto, dentro de una frase.
 *  Altura única de 36 px (la de los campos); `size="row"` la baja a 28 px y solo se usa en acciones de fila de tabla o de tarjeta. */
export function Btn({ kind = "secondary", size, className, icon, style, ...rest }: Props) {
  const row = size === "row";
  const vars = kind === "link" ? {} : ({ "--button-height": row ? "28px" : "36px", "--button-padding-x": row ? "10px" : "14px", "--button-fz": row ? "12px" : "14px" } as CSSProperties);
  return <Button {...(rest as any)} size="sm" leftSection={icon ? <Icon name={icon} size={row ? 14 : 16} /> : undefined} variant={kind === "primary" ? "filled" : kind === "link" || kind === "ghost" ? "subtle" : "default"}
    data-kind={kind} data-compact={row ? "" : undefined} style={{ ...vars, ...style }} className={`ms-btn${className ? ` ${className}` : ""}`} />;
}
