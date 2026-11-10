import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { typeColor } from "./palette";

/** A relation name as words: `HOSTED_ON` and `HostedOn` read «hosted on». Where it is shown, the name as written goes in its tooltip. */
export const humanRelation = (name: string) => name.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/_+/g, " ").trim().toLowerCase();

/** An entity, named the same way everywhere it appears: a chip with the colour of its type (a dot and the edge) and its name as written.
 *  The type is the chip's tooltip and part of its accessible name, so colour is never the only signal. With `to` it is a link; the
 *  entity of the page itself (`current`) is plain, never a link to where you already are. */
export function EntityChip({ name, type, to, current }: { name: string; type?: string | null; to?: string; current?: boolean }) {
  const label = type ? `${name} (${type})` : name;
  const style = { "--ms-type": typeColor(type) } as CSSProperties;
  const body = <><span className="ms-entchip-dot" aria-hidden="true" />{name}</>;
  if (to && !current) return <Link to={to} className="ms-entchip" style={style} title={type ?? undefined} aria-label={label}>{body}</Link>;
  return <span className="ms-entchip" data-current={current ? "" : undefined} style={style} title={type ?? undefined} aria-label={label}>{body}</span>;
}

/** The relation between two entity chips, in words and in the muted style, with the name as written in its tooltip. */
export function RelationWord({ name }: { name: string }) {
  return <span className="ms-relword" title={name}>{humanRelation(name)}</span>;
}
