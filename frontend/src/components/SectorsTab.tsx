// Pestaña «Cuarteles»: cuarteles de corta de la versión guardada. Clic en un tramo del mapa → qué cerrar.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { fmt } from "../lib/format";
import { cutMessage, uidOf } from "../lib/sig";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Help } from "./Fields";

export function SectorsTab() {
  const { project, serverVersion, sectors, sectorFocus, set, net, frame, toast, revision, savedRevision } = useEditor();
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!project || serverVersion === null) return;
    let alive = true;
    setBusy(true);
    api.sectors(project.id).then((r) => alive && set({ sectors: r })).catch((e) => toast(errorText(e), "error")).finally(() => alive && setBusy(false));
    return () => { alive = false; };
  }, [project, serverVersion, set, toast]);
  useEffect(() => () => useEditor.getState().set({ sectorFocus: null }), []);
  if (!project) return null;
  const cur = sectors?.sectors.find((s) => s.id === sectorFocus);
  const show = (id: string) => {
    const s = sectors?.sectors.find((x) => x.id === id);
    set({ sectorFocus: id });
    if (s) frame(s.links.map((l) => uidOf(net, "tramos", l)).filter((u): u is string => !!u), { select: true });
  };
  return (
    <>
      <div className="toolbar">
        <span className="muted small">{busy ? "Calculando…" : `${sectors?.sectors.length ?? 0} cuarteles · versión ${sectors?.model_version ?? "—"}`}
          {revision !== savedRevision ? " · hay cambios sin guardar" : ""}</span>
        <Help text="Un cuartel de corta es el sector que queda aislado al cerrar el conjunto mínimo de válvulas que lo rodea. Haga clic en un tramo del mapa (herramienta Seleccionar) para ver qué válvulas cerrar y cuántos clientes quedan sin agua, incluidos los de aguas abajo. Las válvulas inoperativas se ignoran." />
        {sectorFocus && <button className="small ghost" onClick={() => set({ sectorFocus: null })}>Quitar resaltado</button>}
      </div>
      {cur && (
        <div className="cut-msg">
          <strong>{cur.id}:</strong> {cutMessage(cur.valves, cur.affected_clients)}
          {cur.downstream_clients.length > 0 && <span className="muted"> ({cur.clients.length} en el cuartel y {cur.downstream_clients.length} aguas abajo)</span>}
          <a className="btn small" href={api.sectorExportUrl(project.id, cur.id, "xlsx")}>Excel</a>
          <a className="btn small" href={api.sectorExportUrl(project.id, cur.id, "csv")}>CSV</a>
        </div>
      )}
      {(sectors?.notes ?? []).map((n, i) => <p key={i} className="muted small pad">{n}</p>)}
      <table className="tbl">
        <thead><tr><th>Cuartel</th><th>Válvulas a cerrar</th><th className="num">Red (m)</th><th className="num">Tramos</th><th className="num">Clientes</th><th className="num">Aguas abajo</th><th className="num">Sin agua</th><th className="num">Consumo (L/s)</th></tr></thead>
        <tbody>
          {(sectors?.sectors ?? []).map((s) => (
            <tr key={s.id} className={`clickable ${s.id === sectorFocus ? "current" : ""}`} onClick={() => show(s.id)}>
              <td className="mono">{s.id}{s.has_source ? " ⛲" : ""}</td><td className="mono">{s.valves.join(", ") || "—"}</td>
              <td className="num">{fmt(s.length_m, 0)}</td><td className="num">{s.links.length}</td><td className="num">{s.clients.length}</td>
              <td className="num">{s.downstream_clients.length}</td><td className="num">{s.affected_clients}</td><td className="num">{fmt(s.affected_consumption_lps, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
