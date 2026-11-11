import { create } from "zustand";
import type {
  CatalogPipe, DesignParam, DesignProfile, EngineInfo, HydraulicOptions, NetworkDocument, OrthophotoOut, ProjectOut,
  ScenarioResult, SectorsResult, SimulationResult, ValidationReport, ValveScenario,
} from "../api/types";
import type { Criteria, LinkColorMode } from "../lib/colors";
import { DEFAULT_CRITERIA } from "../lib/colors";
import type { LngLat } from "../lib/geo";
import type { ELink, ENode, Network } from "../lib/network";
import { EMPTY, fromDocument } from "../lib/network";

export type Tool = "select" | "multiselect" | "junction" | "pipe" | "tank" | "reservoir" | "move" | "delete" | "measure"
  | "client" | "shutoff" | "feasibility" | "hydrant" | "well";
export type SimStatus = "idle" | "pending" | "running" | "ok" | "error";
export type MapType = "roadmap" | "terrain" | "satellite" | "hybrid";
export type Theme = "light" | "dark";
export type ThemePref = Theme | "system";

export interface Labels { nodeIds: boolean; linkIds: boolean; pressure: boolean; flow: boolean; velocity: boolean; headloss: boolean; dn: boolean; length: boolean }
export const DEFAULT_LABELS: Labels = { nodeIds: true, linkIds: false, pressure: false, flow: false, velocity: false, headloss: false, dn: false, length: false };

interface Snapshot { net: Network; options: HydraulicOptions }

/** Capas del Resumen: zonas por presión (polígonos coloreados por rango) y área operacional. */
export interface OverlayPolygon { key: string; coords: LngLat[][]; color: string; label?: string }
export interface Overlay { zones: OverlayPolygon[]; area: OverlayPolygon[] }
export const EMPTY_OVERLAY: Overlay = { zones: [], area: [] };

export interface Toast { id: number; text: string; kind: "info" | "error" }

const DEFAULT_OPTIONS: HydraulicOptions = {
  headloss: "H-W", demand_model: "DDA", include_projected_clients: false, minimum_pressure: 0, required_pressure: 15, pressure_exponent: 0.5, extra: {},
  duration_h: null, hydraulic_step_min: 60, pattern_step_min: 60, report_step_min: 60, demand_multiplier: 1, demand_scenario: null,
};

function readPref<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(`trazo.${key}`);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writePref(key: string, value: unknown): void {
  try {
    localStorage.setItem(`trazo.${key}`, JSON.stringify(value));
  } catch {
    /* almacenamiento no disponible */
  }
}

export interface EditorState {
  project: ProjectOut | null;
  serverVersion: number | null;
  lastSavedAt: string | null;
  lastSaveKind: "auto" | "manual" | "import" | null;
  aux: Record<string, string>;
  options: HydraulicOptions;
  net: Network;
  revision: number;
  savedRevision: number;
  past: Snapshot[];
  future: Snapshot[];
  dragging: boolean;
  dragOrigin: Snapshot | null;
  selection: string[];
  tool: Tool;
  catalog: CatalogPipe[];
  profiles: DesignProfile[];
  engine: EngineInfo | null;
  result: SimulationResult | null;
  resultRevision: number | null;
  validation: ValidationReport | null;
  simStatus: SimStatus;
  simError: string | null;
  period: number;
  linkMode: LinkColorMode;
  labels: Labels;
  mapType: MapType;
  theme: Theme;
  themePref: ThemePref;
  defaultProfileId: number | null;
  pendingDelete: string[] | null;
  cameraRequest: { points: LngLat[]; nonce: number } | null;
  toasts: Toast[];
  versionsOpen: boolean;
  /** Escenarios de llaves personalizados (se guardan con la versión). */
  scenarios: ValveScenario[];
  /** Parámetros de diseño efectivos del proyecto. */
  designParams: DesignParam[] | null;
  /** Resultado de escenario mostrado en el mapa (sectores sin agua). */
  scenarioView: ScenarioResult | null;
  /** Punto pendiente de la herramienta Cliente o Factibilidad (abre su diálogo). */
  clientDraft: { pos: LngLat } | null;
  feasibilityDraft: { pos: LngLat; link: string } | null;
  bottomTab: string | null;
  /** Ortofotos del proyecto (capas bajo la red). */
  orthos: OrthophotoOut[];
  /** Cuarteles de corta calculados para la versión guardada y cuartel destacado. */
  sectors: SectorsResult | null;
  sectorFocus: string | null;
  /** Resultado de consulta destacado en el mapa (uids). */
  highlight: string[];
  /** Selección de un punto en el mapa para otro componente (p. ej. puntos de control). */
  mapPick: ((pos: LngLat) => void) | null;
  importOpen: boolean;
  /** El rol del usuario en la organización del proyecto no permite editar (lector o revisor). */
  readOnly: boolean;
  /** Barra de herramientas reducida a íconos y panel inferior plegado (se recuerdan). */
  toolsCollapsed: boolean;
  bottomCollapsed: boolean;
  /** Capas del panel general (Resumen) dibujadas sobre el mapa. */
  overlay: Overlay;

  loadDocument: (project: ProjectOut, doc: NetworkDocument) => void;
  closeProject: () => void;
  commit: (fn: (net: Network) => Network, options?: HydraulicOptions) => void;
  setOptions: (options: HydraulicOptions, fn?: (net: Network) => Network) => void;
  undo: () => void;
  redo: () => void;
  beginDrag: () => void;
  dragTo: (fn: (net: Network) => Network) => void;
  endDrag: () => void;
  select: (uids: string[], additive?: boolean) => void;
  setTool: (tool: Tool) => void;
  requestDelete: (uids: string[]) => void;
  confirmDelete: () => void;
  cancelDelete: () => void;
  focus: (uids: string[]) => void;
  fitAll: () => void;
  toast: (text: string, kind?: Toast["kind"]) => void;
  dismissToast: (id: number) => void;
  set: (partial: Partial<EditorState>) => void;
  setScenarios: (list: ValveScenario[]) => void;
  /** Secciones .inp complementarias (patrones, curvas…): se guardan con la versión siguiente. */
  setAux: (aux: Record<string, string>) => void;
}

const HISTORY_LIMIT = 200;

export function systemTheme(): Theme {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function resolveTheme(pref: ThemePref): Theme {
  return pref === "system" ? systemTheme() : pref;
}
let toastSeq = 0;

/** Criterios para escalas y leyenda: parámetros del proyecto si están cargados; si no, el perfil. */
export function criteriaOf(profile: DesignProfile | undefined, params?: DesignParam[] | null): Criteria {
  if (params?.length) {
    const v = (key: string, fb: number) => {
      const p = params.find((x) => x.key === key);
      return typeof p?.value === "number" ? p.value : fb;
    };
    return {
      pressureMin: v("pressure_min", DEFAULT_CRITERIA.pressureMin), pressureMax: v("pressure_max", DEFAULT_CRITERIA.pressureMax),
      velocityMin: v("velocity_min", DEFAULT_CRITERIA.velocityMin), velocityMax: v("velocity_max", DEFAULT_CRITERIA.velocityMax),
      headlossMax: v("unit_headloss_max", DEFAULT_CRITERIA.headlossMax),
    };
  }
  if (!profile) return DEFAULT_CRITERIA;
  const get = (key: string, field: "min" | "max", fb: number) => {
    const c = profile.criteria.find((x) => x.key === key);
    const v = c?.[field];
    return typeof v === "number" ? v : fb;
  };
  return {
    pressureMin: get("pressure_min", "min", DEFAULT_CRITERIA.pressureMin),
    pressureMax: get("pressure_max", "max", DEFAULT_CRITERIA.pressureMax),
    velocityMin: get("velocity_min", "min", DEFAULT_CRITERIA.velocityMin),
    velocityMax: get("velocity_max", "max", DEFAULT_CRITERIA.velocityMax),
    headlossMax: get("unit_headloss_max", "max", DEFAULT_CRITERIA.headlossMax),
  };
}

function exists(net: Network, u: string): boolean {
  return Boolean(net.nodes[u] || net.links[u] || net.clients[u] || net.shutoffs[u] || net.hydrants[u] || net.wells[u]);
}

function allPoints(net: Network): LngLat[] {
  const pts: LngLat[] = Object.values(net.nodes).map((n) => n.pos);
  for (const l of Object.values(net.links)) pts.push(...l.vertices);
  return pts;
}

/** Elimina elementos y, en cascada, los tramos de los nudos eliminados, sus clientes y las llaves de esos tramos. */
export function removeElements(net: Network, uids: string[]): Network {
  const kill = new Set(uids);
  const nodes: Record<string, ENode> = {};
  for (const [k, n] of Object.entries(net.nodes)) if (!kill.has(k)) nodes[k] = n;
  const links: Record<string, ELink> = {};
  for (const [k, l] of Object.entries(net.links)) {
    if (kill.has(k) || kill.has(l.from) || kill.has(l.to)) continue;
    links[k] = l;
  }
  const clients: Network["clients"] = {};
  for (const [k, c] of Object.entries(net.clients)) if (!kill.has(k) && nodes[c.node]) clients[k] = c;
  const shutoffs: Network["shutoffs"] = {};
  for (const [k, sh] of Object.entries(net.shutoffs)) if (!kill.has(k) && links[sh.link]) shutoffs[k] = sh;
  const hydrants: Network["hydrants"] = {};
  for (const [k, h] of Object.entries(net.hydrants)) if (!kill.has(k) && nodes[h.node]) hydrants[k] = h;
  const wells: Network["wells"] = {};
  for (const [k, w] of Object.entries(net.wells)) if (!kill.has(k)) wells[k] = w.node && !nodes[w.node] ? { ...w, node: null } : w;
  return { nodes, links, clients, shutoffs, hydrants, wells };
}

export const useEditor = create<EditorState>()((set, get) => ({
  project: null,
  serverVersion: null,
  lastSavedAt: null,
  lastSaveKind: null,
  aux: {},
  options: DEFAULT_OPTIONS,
  net: EMPTY,
  revision: 0,
  savedRevision: 0,
  past: [],
  future: [],
  dragging: false,
  dragOrigin: null,
  selection: [],
  tool: "select",
  catalog: [],
  profiles: [],
  engine: null,
  result: null,
  resultRevision: null,
  validation: null,
  simStatus: "idle",
  simError: null,
  period: 0,
  linkMode: readPref<LinkColorMode>("linkMode", "headloss"),
  labels: { ...DEFAULT_LABELS, ...readPref<Partial<Labels>>("labels", {}) },
  mapType: readPref<MapType>("mapType", "roadmap"),
  toolsCollapsed: readPref<boolean>("toolsCollapsed", false),
  bottomCollapsed: readPref<boolean>("bottomCollapsed", false),
  overlay: EMPTY_OVERLAY,
  themePref: readPref<ThemePref>("theme", "system"),
  theme: resolveTheme(readPref<ThemePref>("theme", "system")),
  defaultProfileId: readPref<number | null>("defaultProfileId", null),
  pendingDelete: null,
  cameraRequest: null,
  toasts: [],
  versionsOpen: false,
  scenarios: [],
  designParams: null,
  scenarioView: null,
  clientDraft: null,
  feasibilityDraft: null,
  bottomTab: null,
  orthos: [],
  sectors: null,
  sectorFocus: null,
  highlight: [],
  mapPick: null,
  importOpen: false,
  readOnly: false,

  loadDocument: (project, doc) => {
    const net = fromDocument(doc);
    set({
      project, serverVersion: doc.version, lastSavedAt: doc.created_at, lastSaveKind: doc.kind,
      aux: doc.aux, options: doc.options, net, revision: 0, savedRevision: 0, past: [], future: [],
      dragging: false, dragOrigin: null, selection: [], result: null, resultRevision: null, validation: null,
      simStatus: "idle", simError: null, period: 0, pendingDelete: null, scenarios: doc.scenarios ?? [],
      scenarioView: null, clientDraft: null, feasibilityDraft: null, sectors: null, sectorFocus: null, highlight: [], overlay: EMPTY_OVERLAY,
      cameraRequest: { points: allPoints(net), nonce: Date.now() },
    });
    writePref("lastProject", project.id);
  },
  closeProject: () => set({
    project: null, net: EMPTY, result: null, validation: null, serverVersion: null, revision: 0, savedRevision: 0,
    past: [], future: [], selection: [], simStatus: "idle", simError: null, versionsOpen: false, pendingDelete: null,
    scenarios: [], designParams: null, scenarioView: null, clientDraft: null, feasibilityDraft: null,
    orthos: [], sectors: null, sectorFocus: null, highlight: [], mapPick: null, overlay: EMPTY_OVERLAY,
  }),

  commit: (fn, options) => {
    const s = get();
    if (s.readOnly) {
      if (!s.toasts.some((t) => t.text.startsWith("Solo lectura"))) s.toast("Solo lectura: su rol no permite modificar este proyecto.", "error");
      return;
    }
    const next = fn(s.net);
    if (next === s.net && !options) return;
    set({
      past: [...s.past.slice(-HISTORY_LIMIT + 1), { net: s.net, options: s.options }], future: [],
      net: next, options: options ?? s.options, revision: s.revision + 1,
    });
  },
  setOptions: (options, fn) => get().commit(fn ?? ((n) => n), options),
  undo: () => {
    const s = get();
    const prev = s.past[s.past.length - 1];
    if (!prev) return;
    set({
      past: s.past.slice(0, -1), future: [{ net: s.net, options: s.options }, ...s.future],
      net: prev.net, options: prev.options, revision: s.revision + 1,
      selection: s.selection.filter((u) => exists(prev.net, u)),
    });
  },
  redo: () => {
    const s = get();
    const next = s.future[0];
    if (!next) return;
    set({
      future: s.future.slice(1), past: [...s.past, { net: s.net, options: s.options }],
      net: next.net, options: next.options, revision: s.revision + 1,
      selection: s.selection.filter((u) => exists(next.net, u)),
    });
  },
  beginDrag: () => {
    const s = get();
    set({ dragging: true, dragOrigin: { net: s.net, options: s.options } });
  },
  dragTo: (fn) => set({ net: fn(get().net) }),
  endDrag: () => {
    const s = get();
    if (!s.dragOrigin) return set({ dragging: false });
    const changed = s.dragOrigin.net !== s.net;
    set({
      dragging: false, dragOrigin: null,
      ...(changed ? { past: [...s.past.slice(-HISTORY_LIMIT + 1), s.dragOrigin], future: [], revision: s.revision + 1 } : {}),
    });
  },
  select: (uids, additive = false) => {
    if (!additive) return set({ selection: uids });
    const cur = new Set(get().selection);
    for (const u of uids) {
      if (cur.has(u)) cur.delete(u);
      else cur.add(u);
    }
    set({ selection: [...cur] });
  },
  setTool: (tool) => set({ tool }),
  requestDelete: (uids) => set({ pendingDelete: uids.length ? uids : null }),
  confirmDelete: () => {
    const s = get();
    if (!s.pendingDelete) return;
    const uids = s.pendingDelete;
    s.commit((net) => removeElements(net, uids));
    set({ pendingDelete: null, selection: [] });
  },
  cancelDelete: () => set({ pendingDelete: null }),
  focus: (uids) => {
    const net = get().net;
    const pts: LngLat[] = [];
    for (const u of uids) {
      if (net.nodes[u]) pts.push(net.nodes[u].pos);
      for (const pool of [net.clients, net.hydrants, net.wells] as Record<string, { pos: LngLat }>[]) if (pool[u]) pts.push(pool[u].pos);
      const sh = net.shutoffs[u];
      if (sh && net.links[sh.link]) {
        const l = net.links[sh.link];
        for (const n of [net.nodes[l.from], net.nodes[l.to]]) if (n) pts.push(n.pos);
      }
      const l = net.links[u];
      if (l) {
        const a = net.nodes[l.from];
        const b = net.nodes[l.to];
        if (a) pts.push(a.pos);
        if (b) pts.push(b.pos);
        pts.push(...l.vertices);
      }
    }
    set({ selection: uids, cameraRequest: { points: pts, nonce: Date.now() } });
  },
  fitAll: () => set({ cameraRequest: { points: allPoints(get().net), nonce: Date.now() } }),
  toast: (text, kind = "info") => {
    const id = ++toastSeq;
    set({ toasts: [...get().toasts, { id, text, kind }] });
    window.setTimeout(() => get().dismissToast(id), kind === "error" ? 8000 : 4500);
  },
  dismissToast: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
  set: (partial) => set(partial),
  setScenarios: (list) => set({ scenarios: list, revision: get().revision + 1 }),
  setAux: (aux) => set({ aux, revision: get().revision + 1 }),
}));
