// Secciones plegables de los paneles: qué está abierto se recuerda por usuario (localStorage).
import { create } from "zustand";

interface SectionsState {
  /** Usuario cuyo estado está cargado (clave de almacenamiento). */
  user: string;
  /** Estado elegido por el usuario; sin entrada, rige el valor por defecto de la sección. */
  open: Record<string, boolean>;
  /** Secciones visibles ahora: id → abierta por defecto. */
  mounted: Record<string, boolean>;
  setUser: (user: string) => void;
  isOpen: (id: string, primary?: boolean) => boolean;
  toggle: (id: string, primary?: boolean) => void;
  mount: (id: string, primary: boolean) => void;
  unmount: (id: string) => void;
  setAll: (value: boolean) => void;
}

const key = (user: string) => `trazo.sections.${user || "anon"}`;

function load(user: string): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(key(user));
    const v = raw ? JSON.parse(raw) : {};
    return v && typeof v === "object" ? (v as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

function save(user: string, open: Record<string, boolean>): void {
  try {
    localStorage.setItem(key(user), JSON.stringify(open));
  } catch {
    /* almacenamiento no disponible: el estado vale solo para esta sesión */
  }
}

export const useSections = create<SectionsState>()((set, get) => ({
  user: "",
  open: load(""),
  mounted: {},
  setUser: (user) => {
    if (user !== get().user) set({ user, open: load(user) });
  },
  isOpen: (id, primary = false) => get().open[id] ?? primary,
  toggle: (id, primary = false) => {
    const open = { ...get().open, [id]: !(get().open[id] ?? primary) };
    set({ open });
    save(get().user, open);
  },
  mount: (id, primary) => set((s) => (s.mounted[id] === primary ? s : { mounted: { ...s.mounted, [id]: primary } })),
  unmount: (id) => set((s) => {
    if (!(id in s.mounted)) return s;
    const mounted = { ...s.mounted };
    delete mounted[id];
    return { mounted };
  }),
  setAll: (value) => {
    const open = { ...get().open };
    for (const id of Object.keys(get().mounted)) open[id] = value;
    set({ open });
    save(get().user, open);
  },
}));

/** ¿Están abiertas todas las secciones visibles? */
export function allOpen(s: Pick<SectionsState, "open" | "mounted">): boolean {
  const ids = Object.keys(s.mounted);
  return ids.length > 0 && ids.every((id) => s.open[id] ?? s.mounted[id]);
}
