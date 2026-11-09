import { create } from "zustand";
import type {
  CatalogPipe, DesignProfile, EngineInfo, HydraulicOptions, NetworkDocument, ProjectOut, SimulationResult,
  ValidationReport,
} from "../api/types";
import type { Criteria, LinkColorMode } from "../lib/colors";
import { DEFAULT_CRITERIA } from "../lib/colors";
import type { LngLat } from "../lib/geo";
import type { ELink, ENode, Network } from "../lib/network";
import { EMPTY, fromDocument } from "../lib/network";

export type Tool = "select" | "multiselect" | "junction" | "pipe" | "tank" | "reservoir" | "move" | "delete" | "measure";
export type SimStatus = "idle" | "pending" | "running" | "ok" | "error";
export type MapType = "roadmap" | "terrain" | "satellite" | "hybrid";
export type Theme = "light" | "dark";

export interface Labels { nodeIds: boolean; linkIds: boolean; pressure: boolean; flow: boolean; velocity: boolean; headloss: boolean; dn: boolean }

interface Snapshot { net: Network; options: HydraulicOptions }

export interface Toast { id: number; text: string; kind: "info" | "error" }

const DEFAULT_OPTIONS: HydraulicOptions = {
  headloss: "H-W", demand_model: "DDA", minimum_pressure: 0, required_pressure: 15, pressure_exponent: 0.5, extra: {},
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
  pendingDelete: string[] | null;
  cameraRequest: { points: LngLat[]; nonce: number } | null;
  toasts: Toast[];
  projectsOpen: boolean;
  versionsOpen: boolean;

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
}

const HISTORY_LIMIT = 200;
let toastSeq = 0;

export function criteriaOf(profile: DesignProfile | undefined): Criteria {
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

function allPoints(net: Network): LngLat[] {
  const pts: LngLat[] = Object.values(net.nodes).map((n) => n.pos);
  for (const l of Object.values(net.links)) pts.push(...l.vertices);
  return pts;
}

/** Elimina nudos y, en cascada, los tramos conectados a ellos. */
export function removeElements(net: Network, uids: string[]): Network {
  const kill = new Set(uids);
  const nodes: Record<string, ENode> = {};
  for (const [k, n] of Object.entries(net.nodes)) if (!kill.has(k)) nodes[k] = n;
  const links: Record<string, ELink> = {};
  for (const [k, l] of Object.entries(net.links)) {
    if (kill.has(k) || kill.has(l.from) || kill.has(l.to)) continue;
    links[k] = l;
  }
  return { nodes, links };
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
  labels: readPref<Labels>("labels", { nodeIds: true, linkIds: false, pressure: false, flow: false, velocity: false, headloss: false, dn: false }),
  mapType: readPref<MapType>("mapType", "roadmap"),
  theme: readPref<Theme>("theme", window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
  pendingDelete: null,
  cameraRequest: null,
  toasts: [],
  projectsOpen: false,
  versionsOpen: false,

  loadDocument: (project, doc) => {
    const net = fromDocument(doc);
    set({
      project, serverVersion: doc.version, lastSavedAt: doc.created_at, lastSaveKind: doc.kind,
      aux: doc.aux, options: doc.options, net, revision: 0, savedRevision: 0, past: [], future: [],
      dragging: false, dragOrigin: null, selection: [], result: null, resultRevision: null, validation: null,
      simStatus: "idle", simError: null, period: 0, pendingDelete: null,
      cameraRequest: { points: allPoints(net), nonce: Date.now() },
    });
    writePref("lastProject", project.id);
  },
  closeProject: () => set({ project: null, net: EMPTY, result: null, validation: null, serverVersion: null }),

  commit: (fn, options) => {
    const s = get();
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
      selection: s.selection.filter((u) => prev.net.nodes[u] || prev.net.links[u]),
    });
  },
  redo: () => {
    const s = get();
    const next = s.future[0];
    if (!next) return;
    set({
      future: s.future.slice(1), past: [...s.past, { net: s.net, options: s.options }],
      net: next.net, options: next.options, revision: s.revision + 1,
      selection: s.selection.filter((u) => next.net.nodes[u] || next.net.links[u]),
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
}));
