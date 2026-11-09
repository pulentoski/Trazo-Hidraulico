// Modelo de red del editor (identidad estable por uid) y conversión con el GeoJSON de la API.
import type { HydraulicOptions, LinkFeature, LinkKind, LinkProperties, NetworkDocument, NodeFeature, NodeKind,
  NodeProperties } from "../api/types";
import type { LngLat } from "./geo";
import { polylineLength } from "./geo";

export type NodeProps = Omit<NodeProperties, "element" | "kind" | "uid">;
export type LinkProps = Omit<LinkProperties, "element" | "kind" | "uid" | "from_node" | "to_node">;

export interface ENode { uid: string; id: string; kind: NodeKind; pos: LngLat; props: NodeProps }
export interface ELink { uid: string; id: string; kind: LinkKind; from: string; to: string; vertices: LngLat[]; props: LinkProps }
export interface Network { nodes: Record<string, ENode>; links: Record<string, ELink> }

export const EMPTY: Network = { nodes: {}, links: {} };

export function uid(): string {
  return crypto.randomUUID();
}

export function fromDocument(doc: NetworkDocument): Network {
  const nodes: Record<string, ENode> = {};
  const byLabel: Record<string, string> = {};
  const feats = doc.network.features ?? [];
  for (const f of feats) {
    if (f.properties.element !== "node") continue;
    const nf = f as NodeFeature;
    const { element: _e, kind, uid: u, ...props } = nf.properties;
    const id = u ?? uid();
    nodes[id] = { uid: id, id: nf.id, kind, pos: [nf.geometry.coordinates[0], nf.geometry.coordinates[1]], props };
    byLabel[nf.id] = id;
  }
  const links: Record<string, ELink> = {};
  for (const f of feats) {
    if (f.properties.element !== "link") continue;
    const lf = f as LinkFeature;
    const { element: _e, kind, uid: u, from_node, to_node, ...props } = lf.properties;
    const id = u ?? uid();
    const coords = lf.geometry.coordinates;
    links[id] = {
      uid: id, id: lf.id, kind: kind ?? "pipe", from: byLabel[from_node], to: byLabel[to_node],
      vertices: coords.slice(1, -1).map((c) => [c[0], c[1]] as LngLat), props,
    };
  }
  return { nodes, links };
}

export function linkCoords(net: Network, l: ELink): LngLat[] {
  const a = net.nodes[l.from];
  const b = net.nodes[l.to];
  return [a?.pos ?? l.vertices[0], ...l.vertices, b?.pos ?? l.vertices[l.vertices.length - 1]];
}

export function toFeatureCollection(net: Network) {
  const features: (NodeFeature | LinkFeature)[] = [];
  for (const n of Object.values(net.nodes)) {
    features.push({
      type: "Feature", id: n.id, geometry: { type: "Point", coordinates: [n.pos[0], n.pos[1]] },
      properties: { element: "node", kind: n.kind, uid: n.uid, ...n.props } as NodeProperties,
    });
  }
  for (const l of Object.values(net.links)) {
    const a = net.nodes[l.from];
    const b = net.nodes[l.to];
    if (!a || !b) continue;
    features.push({
      type: "Feature", id: l.id,
      geometry: { type: "LineString", coordinates: linkCoords(net, l).map((p) => [p[0], p[1]] as [number, number]) },
      properties: { element: "link", kind: l.kind, uid: l.uid, from_node: a.id, to_node: b.id, ...l.props } as LinkProperties,
    });
  }
  return { type: "FeatureCollection" as const, features };
}

const PREFIX: Record<NodeKind | LinkKind, string> = { junction: "J", reservoir: "R", tank: "E", pipe: "P", pump: "B", valve: "V" };

export function nextId(existing: Iterable<string>, kind: NodeKind | LinkKind): string {
  const prefix = PREFIX[kind];
  const used = new Set(existing);
  let max = 0;
  for (const id of used) {
    const m = new RegExp(`^${prefix}(\\d+)$`).exec(id);
    if (m) max = Math.max(max, Number(m[1]));
  }
  let n = max + 1;
  while (used.has(`${prefix}${n}`)) n++;
  return `${prefix}${n}`;
}

export function defaultNodeProps(kind: NodeKind, elevation: number | null, source: "manual" | "supuesta"): NodeProps {
  const base: NodeProps = {
    elevation, elevation_source: source,
    elevation_method: source === "supuesta" ? "Copiada del último nudo; verificar" : null,
    base_demand: 0, can_overflow: false, demands: [],
  };
  if (kind === "reservoir") return { ...base, head: elevation !== null ? elevation + 30 : null };
  if (kind === "tank") return { ...base, init_level: 2, min_level: 0.5, max_level: 4, tank_diameter: 10, min_volume: 0 };
  return base;
}

export function defaultPipeProps(p: Partial<LinkProps>): LinkProps {
  return {
    minor_loss: 0, initial_status: "open", length_choice: "slope", ...p,
  } as LinkProps;
}

export function estimatedLength(net: Network, l: ELink): number {
  return polylineLength(linkCoords(net, l));
}

export function roughnessFor(formula: HydraulicOptions["headloss"], c: { hw_c: number; dw_roughness_mm: number; manning_n: number }): number {
  if (formula === "D-W") return c.dw_roughness_mm;
  if (formula === "C-M") return c.manning_n;
  return c.hw_c;
}

export const ROUGHNESS_LABEL: Record<string, string> = {
  "H-W": "Coef. C de Hazen-Williams",
  "D-W": "Rugosidad absoluta ε (mm)",
  "C-M": "Coef. n de Manning",
};
