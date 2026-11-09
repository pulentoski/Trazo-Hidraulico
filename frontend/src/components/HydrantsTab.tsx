// Pestaña «Grifos»: escenario de incendio por grifo (presión residual y caudal disponible).
import { useState } from "react";
import { api } from "../api/client";
import type { FireResult } from "../api/types";
import { fmt } from "../lib/format";
import { uidOf } from "../lib/sig";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Help } from "./Fields";

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
        <table className="tbl">
          <thead><tr><th>Grifo</th><th>Nudo</th><th className="num">Q incendio (L/s)</th><th className="num">P mín. (m)</th><th className="num">P estática (m)</th><th className="num">P residual (m)</th><th className="num">Q disponible (L/s)</th><th>Resultado</th></tr></thead>
          <tbody>
            {hydrants.map((h) => {
              const r = byId.get(h.id);
              return (
                <tr key={h.uid} className="clickable" onClick={() => { const u = uidOf(net, "grifos", h.id); if (u) focus([u]); }}>
                  <td className="mono">{h.id}</td><td className="mono">{net.nodes[h.node]?.id ?? "—"}</td>
                  <td className="num">{fmt(h.props.fire_flow_lps ?? 16, 1)}</td><td className="num">{fmt(h.props.min_pressure_m ?? 5, 1)}</td>
                  <td className="num">{fmt(r?.static_pressure_m ?? NaN, 1)}</td>
                  <td className={`num ${r && r.ok === false ? "bad" : ""}`}>{fmt(r?.residual_pressure_m ?? NaN, 1)}</td>
                  <td className="num">{fmt(r?.available_flow_lps ?? NaN, 1)}</td>
                  <td className={r?.ok === false ? "bad" : ""}>{r?.message ?? ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </>
  );
}
