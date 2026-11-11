// Editor de un proyecto (/proyecto/:id).
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { BottomPanel } from "../components/BottomPanel";
import { ClientDialog } from "../components/ClientDialog";
import { ConfirmDelete, VersionsDialog } from "../components/Dialogs";
import { ExcelImportDialog } from "../components/ExcelImport";
import { FeasibilityDialog } from "../components/FeasibilityDialog";
import { PropertiesPanel } from "../components/PropertiesPanel";
import { TOOLS, ToolPanel } from "../components/ToolPanel";
import { TopBar } from "../components/TopBar";
import { MapView } from "../map/MapView";
import { PATHS } from "../paths";
import { saveNow, simulateNow, startLive, stopLive } from "../state/live";
import { errorText, openProject } from "../state/projects";
import { useEditor } from "../state/store";

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

export function EditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const loaded = useEditor((s) => s.project?.id === id);
  const [failed, setFailed] = useState(false);
  const toolsCollapsed = useEditor((s) => s.toolsCollapsed);
  useShortcuts();

  useEffect(() => {
    if (!id) return;
    let alive = true;
    setFailed(false);
    openProject(id).catch((e) => {
      if (!alive) return;
      setFailed(true);
      useEditor.getState().toast(`No se pudo abrir el proyecto: ${errorText(e)}`, "error");
      navigate(PATHS.home, { replace: true });
    });
    const stop = startLive();
    const warn = (e: BeforeUnloadEvent) => {
      const s = useEditor.getState();
      if (s.revision !== s.savedRevision) e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      alive = false;
      stop();
      stopLive();
      window.removeEventListener("beforeunload", warn);
      useEditor.getState().closeProject();
    };
  }, [id, navigate]);

  return (
    <div className={`app ${toolsCollapsed ? "tools-collapsed" : ""}`}>
      <TopBar />
      <ToolPanel />
      <main className="center">{loaded ? <MapView key={id} /> : <div className="loading">{failed ? "" : "Abriendo proyecto…"}</div>}</main>
      <PropertiesPanel />
      <BottomPanel />
      <VersionsDialog />
      <ConfirmDelete />
      <ClientDialog />
      <FeasibilityDialog />
      <ExcelImportDialog />
    </div>
  );
}
