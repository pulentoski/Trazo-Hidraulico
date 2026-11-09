// Pestaña «Clientes»: tabla, importación desde CSV y exportación.
import { useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { downloadText, toCsv } from "../lib/csv";
import { fmt } from "../lib/format";
import { toLps } from "../lib/network";
import { flushPending } from "../state/live";
import { errorText, openProject } from "../state/projects";
import { useEditor } from "../state/store";
import { CLIENT_TYPES } from "./ClientDialog";
import { Help } from "./Fields";

export function ClientsTab() {
  const { net, result, period, project, focus, toast, designParams } = useEditor();
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const pmin = designParams?.find((p) => p.key === "pressure_min")?.value as number | undefined;
  const typeLabel = Object.fromEntries(CLIENT_TYPES.map((t) => [t.id, t.label]));
  const rows = useMemo(() => Object.values(net.clients).map((c) => {
    const node = net.nodes[c.node];
    let p = node ? result?.nodes[node.id]?.pressure[period] : undefined;
    if (p !== undefined && c.props.elevation != null && node?.props.elevation != null) p += node.props.elevation - c.props.elevation;
    return { c, node: node?.id ?? "—", link: c.link ? net.links[c.link]?.id ?? "—" : "—", lps: toLps(c.props.consumption_value, c.props.consumption_unit), p };
  }).sort((a, b) => a.c.id.localeCompare(b.c.id, "es", { numeric: true })), [net, result, period]);
  const total = rows.filter((r) => r.c.props.status === "activo").reduce((s, r) => s + r.lps, 0);

  const importCsv = async (file: File) => {
    if (!project) return;
    setBusy(true);
    try {
      if (!(await flushPending())) throw new Error("No se pudieron guardar los cambios pendientes.");
      const r = await api.importClients(project.id, file, useEditor.getState().serverVersion);
      await openProject(project.id);
      const far = r.rows.filter((x) => x.warning).length;
      toast(`${r.created} clientes importados (versión ${r.version}).${far ? ` ${far} quedaron a más de 100 m de la red: revíselos.` : ""}`);
    } catch (e) {
      const body = (e as { body?: { detail?: { errors?: string[] } } }).body;
      toast(body?.detail?.errors ? `CSV con errores: ${body.detail.errors.slice(0, 3).join(" ")}` : errorText(e), "error");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const exportCsv = () => downloadText(`clientes-${project?.name ?? "proyecto"}.csv`, toCsv(rows, [
    { header: "ID", value: (r) => r.c.id }, { header: "Nombre", value: (r) => r.c.props.name },
    { header: "lat", value: (r) => r.c.pos[1] }, { header: "lon", value: (r) => r.c.pos[0] },
    { header: "Tipo", value: (r) => r.c.props.client_type }, { header: "Estado", value: (r) => r.c.props.status },
    { header: "Consumo", value: (r) => r.c.props.consumption_value }, { header: "Unidad", value: (r) => r.c.props.consumption_unit },
    { header: "Consumo (L/s)", value: (r) => r.lps }, { header: "Nudo", value: (r) => r.node }, { header: "Tubería", value: (r) => r.link },
    { header: "Presión (m)", value: (r) => r.p },
  ]));

  return (
    <>
      <div className="toolbar">
        <button className="small" disabled={busy || !project} onClick={() => fileRef.current?.click()}>{busy ? "Importando…" : "Importar CSV…"}</button>
        <Help text="Columnas: lat, lon, nombre, consumo (L/s). Opcionales: tipo, estado, unidad (L/s o m3/mes). Separador «,» o «;». Cada cliente se asigna al nudo de consumo más cercano de la tubería más próxima. Si una fila tiene errores no se importa nada." />
        <input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={(e) => e.target.files?.[0] && void importCsv(e.target.files[0])} />
        <button className="small ghost" disabled={!rows.length} onClick={exportCsv}>Exportar CSV</button>
        <span className="muted small">{rows.length} clientes · {fmt(total, 3)} L/s activos</span>
      </div>
      {rows.length === 0 ? <p className="muted pad">Sin clientes. Use la herramienta Cliente (C) o importe un CSV.</p> : (
        <table className="tbl">
          <thead><tr><th>ID</th><th>Nombre o dirección</th><th>Tipo</th><th>Estado</th><th className="num">Consumo</th><th className="num">L/s</th><th>Nudo</th><th>Tubería</th><th className="num">Presión (m)</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.c.uid} className="clickable" onClick={() => focus([r.c.uid])}>
                <td className="mono">{r.c.id}</td><td>{r.c.props.name ?? ""}</td><td>{typeLabel[r.c.props.client_type]}</td>
                <td>{r.c.props.status}</td><td className="num">{fmt(r.c.props.consumption_value, 2)} {r.c.props.consumption_unit === "m3/mes" ? "m³/mes" : "L/s"}</td>
                <td className="num">{fmt(r.lps, 3)}</td><td className="mono">{r.node}</td><td className="mono">{r.link}</td>
                <td className={`num ${r.p !== undefined && pmin !== undefined && r.p < pmin ? "bad" : ""}`}>{fmt(r.p, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
