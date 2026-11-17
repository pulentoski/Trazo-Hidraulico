// Alertas del marco (campana): mantenciones atrasadas por proyecto, desde el listado de proyectos. Se comparte con
// el inicio (que ya trae el listado) y se refresca como máximo una vez por minuto.
import { create } from "zustand";
import { api } from "../api/client";
import type { ProjectOut } from "../api/types";

interface AlertsState {
  projects: ProjectOut[] | null;
  at: number;
  setProjects: (p: ProjectOut[]) => void;
  load: () => Promise<void>;
}

export const useAlerts = create<AlertsState>()((set, get) => ({
  projects: null,
  at: 0,
  setProjects: (projects) => set({ projects, at: Date.now() }),
  load: async () => {
    if (get().projects && Date.now() - get().at < 60_000) return;
    try { set({ projects: await api.listProjects(), at: Date.now() }); } catch { /* sin alertas: no bloquea el marco */ }
  },
}));

/** Proyectos con mantenciones atrasadas, de más a menos. */
export function overdueOf(list: ProjectOut[] | null): ProjectOut[] {
  return (list ?? []).filter((p) => (p.overdue_tasks ?? 0) > 0).sort((a, b) => (b.overdue_tasks ?? 0) - (a.overdue_tasks ?? 0));
}
