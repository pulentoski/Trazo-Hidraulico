import { useEffect } from "react";
import { api } from "./api/client";
import { BottomPanel } from "./components/BottomPanel";
import { ConfirmDelete, ProjectsDialog, Toasts, VersionsDialog, openProject } from "./components/Dialogs";
import { PropertiesPanel } from "./components/PropertiesPanel";
import { TOOLS, ToolPanel } from "./components/ToolPanel";
import { TopBar } from "./components/TopBar";
import { MapView } from "./map/MapView";
import { saveNow, simulateNow, startLive } from "./state/live";
import { useEditor } from "./state/store";

function useShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.closest("input, textarea, select, [contenteditable=true]")) return;
      const st = useEditor.getState();
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); if (e.shiftKey) st.redo(); else st.undo(); return; }
      if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); st.redo(); return; }
      if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); saveNow("Guardado manual"); return; }
      if (e.key === "F5") { e.preventDefault(); simulateNow(); return; }
      if ((e.key === "Delete" || e.key === "Backspace") && st.selection.length) { e.preventDefault(); st.requestDelete(st.selection); return; }
      if (mod || e.altKey) return;
      const t = TOOLS.find((x) => x.key.toLowerCase() === e.key.toLowerCase());
      if (t) st.setTool(t.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

export default function App() {
  const theme = useEditor((s) => s.theme);
  const set = useEditor((s) => s.set);
  useShortcuts();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    const stop = startLive();
    Promise.all([api.catalog(), api.profiles(), api.engine()])
      .then(([catalog, profiles, engine]) => set({ catalog, profiles, engine }))
      .catch(() => useEditor.getState().toast("No fue posible conectar con la API.", "error"));
    let last: string | null = null;
    try { last = JSON.parse(localStorage.getItem("trazo.lastProject") ?? "null"); } catch { last = null; }
    if (last) openProject(last).catch(() => set({ projectsOpen: true }));
    else set({ projectsOpen: true });
    const warn = (e: BeforeUnloadEvent) => {
      const s = useEditor.getState();
      if (s.revision !== s.savedRevision) e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => { stop(); window.removeEventListener("beforeunload", warn); };
  }, [set]);

  return (
    <div className="app">
      <TopBar />
      <ToolPanel />
      <main className="center"><MapView /></main>
      <PropertiesPanel />
      <BottomPanel />
      <ProjectsDialog />
      <VersionsDialog />
      <ConfirmDelete />
      <Toasts />
    </div>
  );
}
