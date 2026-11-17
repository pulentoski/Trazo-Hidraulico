// Pestaña «Grifos»: escenario de incendio por grifo (presión residual y caudal disponible).
import { useState } from "react";
import { api } from "../api/client";
import type { FireResult } from "../api/types";
import { fmt } from "../lib/format";
import { uidOf } from "../lib/sig";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Help } from "./Fields";
import { DataTable } from "./DataTable";

export function HydrantsTab() {
  const { project, net, focus, toast, revision, savedRevision } = useEditor();
  const [res, setRes] = useState<FireResult | null>(null);
  const [busy, setBusy] = useState(false);
  if (!project) return null;
  const hydrants = Object.values(net.hydrants);
  const run = async () => {
    setBusy(true);
    try { setRes(await api.fire(project.id)); } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const byId = new Map((res?.hydrants ?? []).map((h) => [h.id, h]));
  return (
    <>
      <div className="toolbar">
        <button className="small primary" disabled={busy || !hydrants.length || revision !== savedRevision} onClick={() => void run()}>
          {busy ? "Calculando…" : "Escenario de incendio"}</button>
        <Help text="Para cada grifo se agrega su caudal de incendio en el nudo y se simula la red: presión residual (mínima del periodo) y caudal disponible manteniendo la presión residual mínima. Los valores por defecto (16 L/s, 5 m) son referenciales y no están verificados." />
        <span className="muted small">{hydrants.length} grifos{res ? ` · versión ${res.model_version}` : ""}</span>
      </div>
      {!hydrants.length ? <p className="muted pad">Sin grifos. Use la herramienta Grifo (G) o impórtelos desde la planilla.</p> : (
        <DataTable label="Grifos" rows={hydrants} rowKey={(h) => h.uid} initialSort={{ key: "id" }} exportName="grifos"
          onRowClick={(h) => { const u = uidOf(net, "grifos", h.id); if (u) focus([u]); }}
          columns={[
            { key: "id", label: "Grifo", value: (h) => h.id, className: "mono" },
            { key: "node", label: "Nudo", value: (h) => net.nodes[h.node]?.id ?? "", className: "mono" },
            { key: "q", label: "Q incendio (L/s)", type: "num", value: (h) => h.props.fire_flow_lps ?? 16, render: (h) => fmt(h.props.fire_flow_lps ?? 16, 1) },
            { key: "pmin", label: "P mín. (m)", type: "num", value: (h) => h.props.min_pressure_m ?? 5, render: (h) => fmt(h.props.min_pressure_m ?? 5, 1) },
            { key: "ps", label: "P estática (m)", type: "num", value: (h) => byId.get(h.id)?.static_pressure_m ?? null, render: (h) => fmt(byId.get(h.id)?.static_pressure_m ?? NaN, 1) },
            { key: "pr", label: "P residual (m)", type: "num", value: (h) => byId.get(h.id)?.residual_pressure_m ?? null,
              render: (h) => fmt(byId.get(h.id)?.residual_pressure_m ?? NaN, 1), className: (h) => (byId.get(h.id)?.ok === false ? "bad" : "") },
            { key: "qa", label: "Q disponible (L/s)", type: "num", value: (h) => byId.get(h.id)?.available_flow_lps ?? null, render: (h) => fmt(byId.get(h.id)?.available_flow_lps ?? NaN, 1) },
            { key: "msg", label: "Resultado", value: (h) => byId.get(h.id)?.message ?? "", className: (h) => (byId.get(h.id)?.ok === false ? "bad" : "") },
          ]} />
      )}
    </>
  );
}
