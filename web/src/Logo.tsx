// ui-ok-file: marca y tema (colores propios de la identidad)
import { Group, Text, useComputedColorScheme } from "@mantine/core";
import { useId } from "react";

/** Marca MimirSynth: el pozo visto de frente. En el tema Pozo se usa el monocromo claro (el círculo en color se funde con el fondo). */
export function Mark({ size = 32, mono }: { size?: number; mono?: "light" | "ink" }) {
  const uid = useId().replace(/:/g, "");  // id único por instancia: con dos logos en la página (cabecera móvil oculta + barra lateral) un id repetido hacía que la máscara apuntara al oculto y el círculo saliera liso
  const common = { width: size, height: size, viewBox: "0 0 64 64", role: "img", "aria-label": "MimirSynth" } as const;
  if (mono) {
    const id = `cut-${uid}`;
    return (
      <svg {...common}>
        <defs><mask id={id}><rect width="64" height="64" fill="#fff" /><circle cx="32" cy="20" r="6" fill="#000" /><rect x="12" y="31" width="40" height="5" rx="2" fill="#000" /><rect x="17" y="40" width="30" height="5" rx="2" fill="#000" /><rect x="23" y="49" width="18" height="5" rx="2" fill="#000" /></mask></defs>
        <circle cx="32" cy="32" r="30" fill={mono === "light" ? "#F3F6F5" : "#0D1F26"} mask={`url(#${id})`} />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <circle cx="32" cy="32" r="30" fill="#0D1F26" /><circle cx="32" cy="20" r="6" fill="#D4A03A" />
      <rect x="12" y="31" width="40" height="5" rx="2" fill="#CFE4E1" /><rect x="17" y="40" width="30" height="5" rx="2" fill="#5FB8BF" /><rect x="23" y="49" width="18" height="5" rx="2" fill="#1E6B73" />
    </svg>
  );
}

/** Logotipo con nombre, en horizontal: la marca a la izquierda y «MimirSynth» en Oxanium (0,6 × la altura de la marca). */
export default function Logo({ size = 32, name = "MimirSynth" }: { size?: number; name?: string }) {
  const dark = useComputedColorScheme("light") === "dark";
  return (
    <Group gap={Math.round(size / 4)} wrap="nowrap" align="center">
      <Mark size={size} mono={dark ? "light" : undefined} />
      {size >= 24 && <Text component="span" style={{ fontFamily: "var(--ms-display)", fontWeight: 600, fontSize: Math.round(size * 0.6), lineHeight: 1, color: dark ? "var(--ms-espuma, #cfe4e1)" : "var(--ms-ink)" }}>{name}</Text>}
    </Group>
  );
}
