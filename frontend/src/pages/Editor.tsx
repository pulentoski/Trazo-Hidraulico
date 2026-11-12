// Editor de un proyecto (/proyecto/:id).
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
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
import { Skeleton } from "../components/Skeleton";

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
  const [params, setParams] = useSearchParams();
  useShortcuts();

  // «Ver en el mapa» desde Gestión: encuadra y resalta los elementos (con intensidad si es un mapa de calor).
  useEffect(() => {
    if (!loaded || !id || params.get("ver") !== "gestion") return;
    let ref: { type: string; ids: string[]; weights?: Record<string, number> | null; label?: string } | null = null;
    try { ref = JSON.parse(sessionStorage.getItem(`trazo.ver.${id}`) ?? "null"); } catch { ref = null; }
    const next = new URLSearchParams(params);
    next.delete("ver");
    setParams(next, { replace: true });
    if (!ref?.ids?.length) return;
    const st = useEditor.getState();
    const pools: Record<string, Record<string, { id: string; uid: string }>> = {
      node: st.net.nodes, link: st.net.links, client: st.net.clients, shutoff: st.net.shutoffs, hydrant: st.net.hydrants, well: st.net.wells,
    };
    const byId = new Map(Object.values(pools[ref.type] ?? {}).map((e) => [e.id, e.uid]));
    const uids = ref.ids.map((x) => byId.get(x)).filter((u): u is string => !!u);
    if (!uids.length) return;
    let heat: Record<string, number> | null = null;
    if (ref.weights) {
      const max = Math.max(...Object.values(ref.weights), 1e-9);
      heat = {};
      for (const [k, w] of Object.entries(ref.weights)) { const u = byId.get(k); if (u) heat[u] = w / max; }
    }
    st.set({ highlight: heat ? [] : uids, heat, mapNote: `Gestión · ${ref.label ?? "elementos"}: ${uids.length} ${uids.length === 1 ? "elemento" : "elementos"}` });
    st.frame(uids);
  }, [loaded, id, params, setParams]);

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
      <main className="center">{loaded ? <MapView key={id} /> : (failed ? <div className="loading" /> : <Skeleton kind="map" label="Abriendo proyecto…" />)}</main>
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
