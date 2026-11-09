// Modelo de red del editor (identidad estable por uid) y conversión con el GeoJSON de la API.
import type { ClientFeature, ClientProperties, HydraulicOptions, LinkFeature, LinkKind, LinkProperties, NetworkDocument,
  NodeFeature, NodeKind, NodeProperties, ShutoffFeature, ShutoffProperties } from "../api/types";
import type { LngLat } from "./geo";
import { polylineLength } from "./geo";

export type NodeProps = Omit<NodeProperties, "element" | "kind" | "uid">;
export type LinkProps = Omit<LinkProperties, "element" | "kind" | "uid" | "from_node" | "to_node">;

export type ClientProps = Omit<ClientProperties, "element" | "uid" | "node" | "link" | "connection">;
export type ShutoffProps = Pick<ShutoffProperties, "name" | "state">;

export interface ENode { uid: string; id: string; kind: NodeKind; pos: LngLat; props: NodeProps }
export interface ELink { uid: string; id: string; kind: LinkKind; from: string; to: string; vertices: LngLat[]; props: LinkProps }
/** Cliente: `node` y `link` son uids del editor; `connection` es el punto de conexión sobre la tubería. */
export interface EClient { uid: string; id: string; pos: LngLat; node: string; link: string | null; connection: LngLat | null; props: ClientProps }
/** Llave de corte sobre una tubería (`link` = uid), en la fracción `position` de su largo. */
export interface EShutoff { uid: string; id: string; link: string; position: number; props: ShutoffProps }
export interface Network {
  nodes: Record<string, ENode>; links: Record<string, ELink>;
  clients: Record<string, EClient>; shutoffs: Record<string, EShutoff>;
}

export const EMPTY: Network = { nodes: {}, links: {}, clients: {}, shutoffs: {} };

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
  const linkByLabel: Record<string, string> = {};
  for (const l of Object.values(links)) linkByLabel[l.id] = l.uid;
  const clients: Record<string, EClient> = {};
  const shutoffs: Record<string, EShutoff> = {};
  for (const f of feats) {
    if (f.properties.element === "client") {
      const cf = f as ClientFeature;
      const { element: _e, uid: u, node, link, connection, ...props } = cf.properties;
      const id = u ?? uid();
      clients[id] = {
        uid: id, id: cf.id, pos: [cf.geometry.coordinates[0], cf.geometry.coordinates[1]], node: byLabel[node],
        link: link ? linkByLabel[link] ?? null : null, connection: connection ? [connection[0], connection[1]] : null, props,
      };
    } else if (f.properties.element === "shutoff") {
      const sf = f as ShutoffFeature;
      const id = sf.properties.uid ?? uid();
      shutoffs[id] = { uid: id, id: sf.id, link: linkByLabel[sf.properties.link], position: sf.properties.position ?? 0.5,
        props: { name: sf.properties.name ?? null, state: sf.properties.state ?? "open" } };
    }
  }
  return { nodes, links, clients, shutoffs };
}

export function linkCoords(net: Network, l: ELink): LngLat[] {
  const a = net.nodes[l.from];
  const b = net.nodes[l.to];
  return [a?.pos ?? l.vertices[0], ...l.vertices, b?.pos ?? l.vertices[l.vertices.length - 1]];
}

export function toFeatureCollection(net: Network) {
  const features: (NodeFeature | LinkFeature | ClientFeature | ShutoffFeature)[] = [];
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
  for (const c of Object.values(net.clients)) {
    const n = net.nodes[c.node];
    if (!n) continue;
    features.push({
      type: "Feature", id: c.id, geometry: { type: "Point", coordinates: [c.pos[0], c.pos[1]] },
      properties: { element: "client", uid: c.uid, node: n.id, link: c.link ? net.links[c.link]?.id ?? null : null,
        connection: c.connection ? [c.connection[0], c.connection[1]] : null, ...c.props } as ClientProperties,
    });
  }
  for (const sh of Object.values(net.shutoffs)) {
    const l = net.links[sh.link];
    if (!l) continue;
    const p = pointAlong(linkCoords(net, l), sh.position);
    features.push({
      type: "Feature", id: sh.id, geometry: { type: "Point", coordinates: [p[0], p[1]] },
      properties: { element: "shutoff", uid: sh.uid, link: l.id, position: sh.position, ...sh.props } as ShutoffProperties,
    });
  }
  return { type: "FeatureCollection" as const, features };
}

const PREFIX: Record<NodeKind | LinkKind | "client" | "shutoff", string> = {
  junction: "J", reservoir: "R", tank: "E", pipe: "P", pump: "B", valve: "V", client: "C", shutoff: "LL",
};

export function nextId(existing: Iterable<string>, kind: NodeKind | LinkKind | "client" | "shutoff"): string {
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

/**
 * Propiedades de un nudo nuevo. La cota queda vacía (nunca se supone): la validación la marca como
 * error bloqueante hasta que se ingrese. Lo mismo la carga de un reservorio.
 */
export function defaultNodeProps(kind: NodeKind): NodeProps {
  const base: NodeProps = {
    elevation: null, elevation_source: "manual", elevation_method: null,
    base_demand: 0, can_overflow: false, demands: [],
  };
  if (kind === "reservoir") return { ...base, head: null };
  if (kind === "tank") return { ...base, init_level: 2, min_level: 0.5, max_level: 4, tank_diameter: 10, min_volume: 0 };
  return base;
}

/** Datos derivados de un estanque cilíndrico (o con curva de volumen, sin volumen calculable). */
export function tankStorage(p: Pick<NodeProps, "elevation" | "max_level" | "min_level" | "tank_diameter" | "min_volume" | "volume_curve">,
  level: number | null | undefined): { overflowElevation: number | null; volume: number | null } {
  const overflowElevation = p.elevation != null && p.max_level != null ? p.elevation + p.max_level : null;
  let volume: number | null = null;
  if (!p.volume_curve && p.tank_diameter && p.tank_diameter > 0 && level != null && Number.isFinite(level)) {
    const area = (Math.PI / 4) * p.tank_diameter ** 2;
    const hmin = p.min_level ?? 0;
    // Igual que EPANET: V = Vmín + A·(h − hmín), con Vmín = A·hmín si no se indicó volumen mínimo.
    const vmin = p.min_volume && p.min_volume > 0 ? p.min_volume : area * hmin;
    volume = vmin + area * (level - hmin);
  }
  return { overflowElevation, volume };
}

export function defaultPipeProps(p: Partial<LinkProps>): LinkProps {
  return {
    minor_loss: 0, initial_status: "open", length_choice: "slope", inner_diameter_source: "catalogo", ...p,
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

// ── Clientes, llaves y conexión a la red ──

/** m³/mes → L/s con mes de 30 días (igual que la API). */
export const SECONDS_PER_MONTH = 30 * 86400;
export function toLps(value: number, unit: ClientProps["consumption_unit"]): number {
  return unit === "m3/mes" ? (value * 1000) / SECONDS_PER_MONTH : value;
}

/** Metros locales (equirrectangular) alrededor de `origin`: suficiente para conectar y medir a escala de calle. */
function meters(origin: LngLat) {
  const kx = 111320 * Math.cos((origin[1] * Math.PI) / 180);
  const ky = 110540;
  return {
    to: (p: LngLat): [number, number] => [(p[0] - origin[0]) * kx, (p[1] - origin[1]) * ky],
    from: (q: [number, number]): LngLat => [origin[0] + q[0] / kx, origin[1] + q[1] / ky],
  };
}

/** Punto a una fracción del largo de una polilínea. */
export function pointAlong(coords: LngLat[], fraction: number): LngLat {
  if (coords.length < 2) return coords[0];
  const m = meters(coords[0]);
  const pts = coords.map(m.to);
  const lens = pts.slice(1).map((q, i) => Math.hypot(q[0] - pts[i][0], q[1] - pts[i][1]));
  let target = Math.max(0, Math.min(1, fraction)) * lens.reduce((a, b) => a + b, 0);
  for (let i = 0; i < lens.length; i++) {
    if (target <= lens[i] || i === lens.length - 1) {
      const t = lens[i] === 0 ? 0 : Math.min(1, target / lens[i]);
      return m.from([pts[i][0] + t * (pts[i + 1][0] - pts[i][0]), pts[i][1] + t * (pts[i + 1][1] - pts[i][1])]);
    }
    target -= lens[i];
  }
  return coords[coords.length - 1];
}

export interface PipeProjection { link: string; point: LngLat; segment: number; fraction: number; distanceM: number }

/** Proyección de un punto sobre una tubería (uid). */
export function projectOnLink(net: Network, linkUid: string, pos: LngLat): PipeProjection {
  const coords = linkCoords(net, net.links[linkUid]);
  const m = meters(pos);
  const pts = coords.map(m.to);
  const lens = pts.slice(1).map((q, i) => Math.hypot(q[0] - pts[i][0], q[1] - pts[i][1]));
  const total = lens.reduce((a, b) => a + b, 0);
  let best = { d: Infinity, seg: 0, q: pts[0], along: 0 };
  let acc = 0;
  for (let i = 0; i < lens.length; i++) {
    const [a, b] = [pts[i], pts[i + 1]];
    const L2 = lens[i] ** 2;
    const t = L2 === 0 ? 0 : Math.max(0, Math.min(1, ((-a[0]) * (b[0] - a[0]) + (-a[1]) * (b[1] - a[1])) / L2));
    const q: [number, number] = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
    const d = Math.hypot(q[0], q[1]);
    if (d < best.d) best = { d, seg: i, q, along: acc + t * lens[i] };
    acc += lens[i];
  }
  return { link: linkUid, point: m.from(best.q), segment: best.seg, fraction: total > 0 ? best.along / total : 0, distanceM: best.d };
}

/** Tubería más cercana a un punto (solo tuberías). */
export function nearestPipe(net: Network, pos: LngLat): PipeProjection | null {
  let best: PipeProjection | null = null;
  for (const l of Object.values(net.links)) {
    if (l.kind !== "pipe" || !net.nodes[l.from] || !net.nodes[l.to]) continue;
    const pr = projectOnLink(net, l.uid, pos);
    if (!best || pr.distanceM < best.distanceM) best = pr;
  }
  return best;
}

/** Nudo de consumo más cercano al punto de conexión: extremos de la tubería; si no son de consumo, el más cercano. */
export function nearestJunction(net: Network, pr: PipeProjection): { node: string; distanceM: number } | null {
  const l = net.links[pr.link];
  const m = meters(pr.point);
  const dist = (n: ENode) => Math.hypot(...m.to(n.pos));
  const ends = [net.nodes[l.from], net.nodes[l.to]].filter((n) => n && n.kind === "junction");
  const pool = ends.length ? ends : Object.values(net.nodes).filter((n) => n.kind === "junction");
  if (!pool.length) return null;
  const n = pool.reduce((a, b) => (dist(b) < dist(a) ? b : a));
  return { node: n.uid, distanceM: dist(n) };
}

/** Cota sugerida en el punto de conexión (interpolada entre los extremos); se muestra, nunca se asigna sola. */
export function interpolatedElevation(net: Network, pr: PipeProjection): number | null {
  const l = net.links[pr.link];
  const a = net.nodes[l.from]?.props.elevation;
  const b = net.nodes[l.to]?.props.elevation;
  return a == null || b == null ? null : a + (b - a) * pr.fraction;
}

/**
 * Divide la tubería en el punto de conexión con un nudo nuevo (cota dada; puede ser null y entonces la
 * validación la exige). Las partes heredan las propiedades; un largo manual se reparte en proporción.
 */
export function splitPipe(net: Network, pr: PipeProjection, nodeId: string, elevation: number | null): { net: Network; node: string; second: string } {
  const l = net.links[pr.link];
  const nodeUid = uid();
  const secondUid = uid();
  const coords = linkCoords(net, l);
  const firstVerts = coords.slice(1, pr.segment + 1);
  const secondVerts = coords.slice(pr.segment + 1, -1);
  const node: ENode = { uid: nodeUid, id: nodeId, kind: "junction", pos: pr.point, props: { ...defaultNodeProps("junction"), elevation,
    elevation_method: elevation == null ? null : "Ingreso manual al conectar" } };
  const manual = l.props.length_choice === "manual" && l.props.length_hydraulic_m;
  const total = manual ? l.props.length_hydraulic_m! : null;
  const first: ELink = { ...l, to: nodeUid, vertices: firstVerts,
    props: { ...l.props, ...(total != null ? { length_hydraulic_m: total * pr.fraction } : {}) } };
  const second: ELink = { ...l, uid: secondUid, id: nextId(Object.values(net.links).map((x) => x.id), "pipe"), from: nodeUid,
    vertices: secondVerts, props: { ...l.props, ...(total != null ? { length_hydraulic_m: total * (1 - pr.fraction) } : {}) } };
  const shutoffs = { ...net.shutoffs };
  for (const [k, sh] of Object.entries(shutoffs)) {
    if (sh.link !== l.uid) continue;
    shutoffs[k] = sh.position <= pr.fraction && pr.fraction > 0
      ? { ...sh, position: sh.position / pr.fraction }
      : { ...sh, link: secondUid, position: pr.fraction < 1 ? (sh.position - pr.fraction) / (1 - pr.fraction) : 0 };
  }
  return {
    net: { ...net, nodes: { ...net.nodes, [nodeUid]: node }, links: { ...net.links, [l.uid]: first, [secondUid]: second }, shutoffs },
    node: nodeUid, second: secondUid,
  };
}

/** Demanda del nudo con trazabilidad: manual + clientes (activos; proyectados si la opción lo indica). */
export function nodeDemand(net: Network, nodeUid: string, includeProjected: boolean) {
  const n = net.nodes[nodeUid];
  const manual = (n?.props.base_demand ?? 0) + (n?.props.demands ?? []).reduce((s, d) => s + d.base, 0);
  const clients = Object.values(net.clients).filter((c) => c.node === nodeUid);
  const counted = clients.filter((c) => c.props.status === "activo" || includeProjected);
  const fromClients = counted.reduce((s, c) => s + toLps(c.props.consumption_value, c.props.consumption_unit), 0);
  return { manual, clients, counted, fromClients, total: manual + fromClients };
}
