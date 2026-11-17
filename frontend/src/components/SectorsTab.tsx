// Pestaña «Cuarteles»: cuarteles de corta de la versión guardada. Clic en un tramo del mapa → qué cerrar.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { fmt } from "../lib/format";
import { cutMessage, uidOf } from "../lib/sig";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Help } from "./Fields";
import { DataTable } from "./DataTable";

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
      <DataTable label="Cuarteles" rows={sectors?.sectors ?? []} rowKey={(s) => s.id} onRowClick={(s) => show(s.id)}
        rowClassName={(s) => (s.id === sectorFocus ? "current" : "")} initialSort={{ key: "id" }} exportName={`cuarteles-${project.name}`}
        empty={<p className="muted pad">{busy ? "Calculando…" : "Sin cuarteles."}</p>}
        columns={[
          { key: "id", label: "Cuartel", value: (s) => s.id, render: (s) => `${s.id}${s.has_source ? " ⛲" : ""}`, className: "mono" },
          { key: "valves", label: "Válvulas a cerrar", value: (s) => s.valves.join(", "), className: "mono" },
          { key: "len", label: "Red (m)", type: "num", value: (s) => s.length_m, render: (s) => fmt(s.length_m, 0) },
          { key: "links", label: "Tramos", type: "num", value: (s) => s.links.length },
          { key: "clients", label: "Clientes", type: "num", value: (s) => s.clients.length },
          { key: "down", label: "Aguas abajo", type: "num", value: (s) => s.downstream_clients.length },
          { key: "aff", label: "Sin agua", type: "num", value: (s) => s.affected_clients },
          { key: "lps", label: "Consumo (L/s)", type: "num", value: (s) => s.affected_consumption_lps, render: (s) => fmt(s.affected_consumption_lps, 3) },
        ]} />
    </>
  );
}
