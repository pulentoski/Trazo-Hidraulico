// Sesión del usuario: datos de /api/auth/me, rol en cada organización y organización activa.
import { create } from "zustand";
import { api } from "../api/client";
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
    } catch {
      set({ me: null, status: "anon" });
      return null;
    }
  },
  roleIn: (org) => get().me?.orgs.find((o) => o.id === org)?.role ?? null,
}));

export const ROLE_LABEL: Record<Role, string> = { admin: "Administrador", proyectista: "Proyectista", revisor: "Revisor", lector: "Lector" };
export const canEdit = (role: Role | null) => role === "admin" || role === "proyectista";
export const canReview = (role: Role | null) => role === "admin" || role === "revisor";
