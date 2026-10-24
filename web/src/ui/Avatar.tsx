import { Avatar as MAvatar } from "@mantine/core";

/** Avatar de una persona: su imagen o, si no la tiene, sus iniciales. */
export function Avatar({ src, name, size = 32 }: { src?: string; name: string; size?: number }) {
  const initials = (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "?";
  return <MAvatar src={src || undefined} alt={name} size={size} radius={6} className="ms-avatar" data-img={src ? "" : undefined}>{initials}</MAvatar>;
}
