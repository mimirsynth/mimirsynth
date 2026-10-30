/** Lo que los lienzos del grafo (2D y 3D) necesitan de cada nodo y arista; el resto de la pantalla no ve d3, three ni el canvas. */
import type { Layout } from "./layouts";

/** `groups`: claves de los halos (orígenes) a los que pertenece el nodo; `ring`: respaldado por 2 o más orígenes. */
export type RNode = { id: string; color: string; size: number; caption: string; visible: boolean; groups?: string[]; ring?: boolean; tooltip?: string };
/** `strong`: hecho respaldado por 2 o más orígenes (se dibuja más grueso, o más brillante en 3D). */
export type RLink = { id: string; source: string; target: string; label: string; color: string; dashed: boolean; visible: boolean; strong?: boolean };
/** Halo de un origen: envuelve a sus nodos y los atrae hacia su ancla. El orden es el de la leyenda. */
export type RHalo = { key: string; name: string; color: string };
/** Efectos gráficos: «full» con todo; «reduced» sin entrada animada, partículas ni minimapa y con menos textos (los halos se quedan). */
export type Effects = "full" | "reduced";
export type EffectsMode = "auto" | Effects;
export type RendererEvents = {
  /** Nodo bajo el puntero (o null) y su posición en pantalla, para el tooltip. */
  hover?: (id: string | null, x: number, y: number) => void;
  /** Cambia el modo efectivo (en automático, al medir fotogramas lentos). */
  effects?: (e: Effects) => void;
  /** El 3D sigue lento incluso con los efectos reducidos: la pantalla sugiere volver a 2D. */
  slow?: () => void;
  nodeClick?: (id: string) => void;
  nodeContextMenu?: (id: string) => void;
  linkClick?: (id: string) => void;
  backgroundClick?: () => void;
};

/** Lo que `GraphCanvas` pide a un lienzo, sea 2D o 3D. */
export interface GraphRenderer {
  setEvents(events: RendererEvents): void;
  setEffects(mode: EffectsMode): void;
  setLayout(layout: Layout, root?: string): void;
  resize(w: number, h: number): void;
  setData(nodes: RNode[], links: RLink[], halos?: RHalo[]): void;
  setSelection(node: string | null, link: string | null): void;
  setPaused(p: boolean): void;
  fit(ms?: number, only?: (id: string) => boolean): void;
  /** Suelta los nodos fijados al arrastrarlos y recoloca el grafo. */
  resetPositions(): void;
  toPng(): string;
  destroy(): void;
}

export const SLOW_MS = 34;              // un fotograma más largo que esto (menos de ~30 fps) cuenta como lento…
export const SLOW_FRAMES = 45;          // …y tantos seguidos (unos 2 s de animación) bajan el modo automático a reducido
export const MAX_LABELS = 120;          // textos por fotograma: el texto con contorno es lo más caro de dibujar (sobre todo sin GPU)
export const MAX_LABELS_REDUCED = 60;
export const ENTER_MS = 450;            // entrada de un nodo nuevo: aparece y crece
export const DIM = 0.15;                // opacidad de lo que queda fuera del foco
export const FOCUS_DELAY = 250;         // el ratón tiene que quedarse este tiempo sobre un nodo para enfocarlo: cruzar nodos de paso no cambia nada
export const FADE_MS = 350;             // el atenuado del foco entra y sale con un fundido, nunca de golpe (WCAG 2.3.1 y 2.3.3)
export const PARTICLE_MS = 6000;        // lo que tarda una partícula en recorrer su arista
export const FOLLOW_MS = 4000;          // un encuadre sigue a la simulación como mucho este tiempo
export const MORPH_MS = 600;            // cambio de disposición: cada nodo viaja a su sitio nuevo
export const PULL = 0.15;               // fuerza hacia el ancla de los orígenes: alta para que un origen con pocos enlaces no se disperse
export const PULL_NONE = 0.04;
export const LINK = 0.3;
export const LINK_WITH_HALOS = 0.08;
export const CHARGE = -220;
export const CHARGE_WITH_HALOS = -90;   // con halos, la repulsión no debe deshacer los grupos
/** Curva de ida y vuelta para zoom y cambios de disposición. */
export const ease = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
