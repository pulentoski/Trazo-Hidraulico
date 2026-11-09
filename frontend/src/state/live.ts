// Guardado automático + simulación casi en vivo.
//
// - Cada cambio confirmado incrementa `revision`. Tras 400 ms sin cambios (y nunca durante un arrastre)
//   se guarda la red: el servidor crea una versión inmutable y devuelve su número (model_version).
// - Se simula exactamente esa versión. La respuesta solo se acepta si sigue correspondiendo al modelo
//   vigente (misma versión y sin ediciones posteriores); si no, se descarta por obsoleta.
// - Solo hay una operación en curso; las ediciones que llegan mientras tanto programan otro ciclo.
import { api, ApiError } from "../api/client";
import type { SimulationBlocked, SimulationResult } from "../api/types";
import { toFeatureCollection } from "../lib/network";
import { useEditor } from "./store";

export const DEBOUNCE_MS = 400;

let timer: number | undefined;
let busy = false;
let again = false;
let pendingManual: { label: string | null } | null = null;
let forceSimulate = false;

const st = () => useEditor.getState();

export function scheduleLive(): void {
  const s = st();
  if (!s.project || s.revision === s.savedRevision) return;
  window.clearTimeout(timer);
  st().set({ simStatus: "pending", simError: null });
  if (s.dragging) return; // se reprograma al soltar
  timer = window.setTimeout(() => void cycle(), DEBOUNCE_MS);
}

/** Guardado manual (crea una versión con etiqueta) y simulación inmediata. */
export function saveNow(label: string | null): void {
  pendingManual = { label };
  window.clearTimeout(timer);
  void cycle();
}

/** Simulación inmediata (guarda antes si hay cambios pendientes). */
export function simulateNow(): void {
  forceSimulate = true;
  window.clearTimeout(timer);
  void cycle();
}

export async function simulateVersion(version: number, revision: number): Promise<void> {
  const s = st();
  if (!s.project) return;
  st().set({ simStatus: "running", simError: null });
  const out: SimulationResult | SimulationBlocked = await api.simulate(s.project.id, version);
  const now = st();
  // Respuesta obsoleta: otra versión o ediciones posteriores → se descarta.
  if (now.serverVersion !== version || now.revision !== revision) return;
  if ("status" in out && out.status === "blocked") {
    const n = out.validation.errors.length;
    st().set({
      validation: out.validation, result: null, resultRevision: null, simStatus: "error",
      simError: `La red tiene ${n} ${n === 1 ? "error bloqueante" : "errores bloqueantes"}: no se simuló.`,
    });
    return;
  }
  const res = out as SimulationResult;
  st().set({
    result: res, validation: res.validation, resultRevision: revision,
    period: Math.min(now.period, Math.max(0, res.times.length - 1)),
    simStatus: res.status === "error" ? "error" : "ok",
    simError: res.status === "error" ? (res.messages.find((m) => m.severity === "error")?.message ?? "Error del motor") : null,
  });
}

async function cycle(): Promise<void> {
  if (busy) {
    again = true;
    return;
  }
  busy = true;
  try {
    for (;;) {
      const s = st();
      if (!s.project || s.dragging) break;
      const manual = pendingManual;
      pendingManual = null;
      const dirty = s.revision !== s.savedRevision;
      if (!dirty && !manual) {
        if (forceSimulate && s.serverVersion) {
          forceSimulate = false;
          await simulateVersion(s.serverVersion, s.revision);
        }
        break;
      }
      const rev = s.revision;
      st().set({ simStatus: "running", simError: null });
      const res = await api.saveNetwork(s.project.id, {
        base_version: s.serverVersion, kind: manual ? "manual" : "auto", label: manual?.label ?? null,
        options: s.options, aux: s.aux, network: toFeatureCollection(s.net),
      });
      // Largos recalculados por el servidor (sin crear entrada de historial).
      const cur = st();
      const links = { ...cur.net.links };
      for (const [k, l] of Object.entries(links)) {
        const len = res.lengths[l.id];
        if (len) links[k] = { ...l, props: { ...l.props, ...len } };
      }
      st().set({
        serverVersion: res.version, savedRevision: rev, lastSavedAt: new Date().toISOString(),
        lastSaveKind: manual ? "manual" : "auto", net: { ...cur.net, links },
      });
      if (manual) st().toast(res.created ? `Versión ${res.version} guardada.` : `Sin cambios: se mantiene la versión ${res.version}.`);
      if (st().revision !== rev) continue; // hubo ediciones durante el guardado
      forceSimulate = false;
      await simulateVersion(res.version, rev);
      break;
    }
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : "No fue posible comunicarse con la API";
    st().set({ simStatus: "error", simError: msg });
    if (err instanceof ApiError && err.status === 422 && err.body && typeof err.body === "object" && "validation" in err.body) {
      st().set({ validation: (err.body as { validation: SimulationResult["validation"] }).validation });
    }
    if (err instanceof ApiError && err.status === 409) st().toast(msg, "error");
  } finally {
    busy = false;
    if (again) {
      again = false;
      scheduleLive();
    }
  }
}

/** Suscripción: cualquier cambio de revisión o fin de arrastre programa el ciclo. */
export function startLive(): () => void {
  return useEditor.subscribe((s, prev) => {
    if (s.revision !== prev.revision || (prev.dragging && !s.dragging)) scheduleLive();
  });
}
