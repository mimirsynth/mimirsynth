import { useTranslation } from "react-i18next";
import { Tooltip as MTooltip, useComputedColorScheme, useMantineColorScheme } from "@mantine/core";
import { Icon } from "./Icon";

/** Interruptor de tema claro/oscuro: pastilla con una bola que se desliza entre el sol y la luna. */
export function ThemeToggle() {
  const { t } = useTranslation();
  const { setColorScheme } = useMantineColorScheme();
  const dark = useComputedColorScheme("light", { getInitialValueInEffect: true }) === "dark";
  return (
    <button type="button" role="switch" aria-checked={dark} aria-label={t("Tema oscuro")} title={dark ? t("Cambiar a tema claro") : t("Cambiar a tema oscuro")}
      className="ms-toggle" data-dark={dark ? "" : undefined} onClick={() => setColorScheme(dark ? "light" : "dark")}>
      <span className="ms-toggle-icon ms-toggle-sun"><Icon name="sun" size={15} stroke={2.2} /></span>
      <span className="ms-toggle-icon ms-toggle-moon"><Icon name="moon" size={15} stroke={2.2} /></span>
      <span className="ms-toggle-thumb" aria-hidden="true" />
    </button>
  );
}

/** Versión compacta: un icono que alterna entre claro y oscuro (para la barra lateral). */
export function ThemeButton() {
  const { t } = useTranslation();
  const { setColorScheme } = useMantineColorScheme();
  const dark = useComputedColorScheme("light", { getInitialValueInEffect: true }) === "dark";
  const label = dark ? t("Cambiar a tema claro") : t("Cambiar a tema oscuro");
  return (
    <MTooltip label={label} position="top">
      <button type="button" aria-label={label} className="ms-roundbtn" onClick={() => setColorScheme(dark ? "light" : "dark")}><Icon name={dark ? "sun" : "moon"} size={18} /></button>
    </MTooltip>
  );
}
