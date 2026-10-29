// d3-force-3d no trae tipos: tiene la misma interfaz que d3-force, más la tercera dimensión (forceZ y el número de dimensiones).
declare module "d3-force-3d" {
  import type { Simulation, SimulationLinkDatum, SimulationNodeDatum } from "d3-force";
  export { forceCollide, forceLink, forceManyBody, forceRadial, forceX, forceY } from "d3-force";
  export function forceSimulation<N extends SimulationNodeDatum, L extends SimulationLinkDatum<N> = SimulationLinkDatum<N>>(nodes?: N[], numDimensions?: number): Simulation<N, L>;
  export function forceZ<N extends SimulationNodeDatum>(z?: number | ((d: N, i: number, data: N[]) => number)): {
    (alpha: number): void; z(z: (d: N) => number): any; strength(s: number | ((d: N) => number)): any;
  };
}
