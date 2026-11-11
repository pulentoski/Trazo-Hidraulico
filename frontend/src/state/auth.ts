// Sesión del usuario: datos de /api/auth/me, rol en cada organización y organización activa.
import { create } from "zustand";
import { ApiError, api } from "../api/client";
import type { Me, Role } from "../api/types";

interface AuthState {
  me: Me | null;
  status: "loading" | "ok" | "anon";
  refresh: () => Promise<Me | null>;
  roleIn: (org: string | null | undefined) => Role | null;
}

export const useAuth = create<AuthState>()((set, get) => ({
  me: null,
  status: "loading",
  refresh: async () => {
    try {
      const me = await api.me();
      set({ me, status: "ok" });
      return me;
    } catch (e) {
      // Solo un 401 significa «sin sesión». Un 429 (tras los reintentos), un error del servidor o de red no
      // cierran la sesión: se conserva lo conocido y se vuelve a consultar.
      if (e instanceof ApiError && e.status === 401) {
        set({ me: null, status: "anon" });
        return null;
      }
      window.setTimeout(() => { void get().refresh(); }, 5000);
      return get().me;
    }
  },
  roleIn: (org) => get().me?.orgs.find((o) => o.id === org)?.role ?? null,
}));

export const ROLE_LABEL: Record<Role, string> = { admin: "Administrador", proyectista: "Proyectista", revisor: "Revisor", lector: "Lector" };
export const canEdit = (role: Role | null) => role === "admin" || role === "proyectista";
export const canReview = (role: Role | null) => role === "admin" || role === "revisor";
