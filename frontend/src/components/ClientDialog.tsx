// Alta de un cliente: se proyecta sobre la tubería más cercana y se conecta al nudo más cercano o a un nudo nuevo.
import { useMemo, useState } from "react";
import { fmt, parseNum } from "../lib/format";
import type { ClientProps, EClient } from "../lib/network";
import { interpolatedElevation, nearestJunction, nearestPipe, nextId, splitPipe, toLps, uid } from "../lib/network";
import { useEditor } from "../state/store";
import { Modal } from "./Dialogs";
import { Help } from "./Fields";

export const CLIENT_TYPES: { id: ClientProps["client_type"]; label: string }[] = [
  { id: "residencial", label: "Residencial" }, { id: "comercial", label: "Comercial" },
  { id: "industrial", label: "Industrial" }, { id: "publico", label: "Público" },
];

export function ClientDialog() {
  const draft = useEditor((s) => s.clientDraft);
  if (!draft) return null;
  return <ClientForm pos={draft.pos} />;
}

function ClientForm({ pos }: { pos: [number, number] }) {
  const { net, set, commit, select, toast } = useEditor();
  const pr = useMemo(() => nearestPipe(net, pos), [net, pos]);
  const near = useMemo(() => (pr ? nearestJunction(net, pr) : null), [net, pr]);
  const interp = pr ? interpolatedElevation(net, pr) : null;
  const [name, setName] = useState("");
  const [type, setType] = useState<ClientProps["client_type"]>("residencial");
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState<ClientProps["consumption_unit"]>("L/s");
  const [status, setStatus] = useState<ClientProps["status"]>("activo");
  const [mode, setMode] = useState<ClientProps["connection_mode"]>(near ? "nearest" : "new_node");
  const [elev, setElev] = useState("");
  const close = () => set({ clientDraft: null });
  if (!pr) return null;
  const link = net.links[pr.link];
  const v = parseNum(value);
  const e = parseNum(elev);
  const valid = v !== null && v >= 0 && (mode === "nearest" ? !!near : e !== null);

  const save = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!valid) return;
    const id = nextId(Object.values(net.clients).map((c) => c.id), "client");
    commit((n) => {
      let next = n;
      let nodeUid = near?.node ?? "";
      if (mode === "new_node") {
        const r = splitPipe(n, pr, nextId(Object.values(n.nodes).map((x) => x.id), "junction"), e);
        next = r.net;
        nodeUid = r.node;
      }
      const c: EClient = { uid: uid(), id, pos, node: nodeUid, link: pr.link, connection: pr.point, props: {
        name: name.trim() || null, client_type: type, status, consumption_value: v!, consumption_unit: unit,
        connection_mode: mode, elevation: mode === "new_node" ? e : null } };
      return { ...next, clients: { ...next.clients, [c.uid]: c } };
    });
    const created = Object.values(useEditor.getState().net.clients).find((c) => c.id === id);
    if (created) select([created.uid]);
    toast(`Cliente ${id} agregado.`);
    close();
  };

  return (
    <Modal title="Nuevo cliente" onClose={close}>
      <form onSubmit={save}>
        <label className="field"><span>Nombre o dirección</span><input autoFocus value={name} onChange={(x) => setName(x.target.value)} placeholder="Ej.: Los Aromos 123" /></label>
        <label className="field"><span>Tipo</span>
          <select value={type} onChange={(x) => setType(x.target.value as ClientProps["client_type"])}>{CLIENT_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select>
        </label>
        <label className={`field ${value && v === null ? "invalid" : ""}`}><span>Consumo <Help text="Consumo medio del cliente. En m³/mes se convierte a L/s con mes de 30 días." /></span>
          <div className="with-unit">
            <input inputMode="decimal" value={value} onChange={(x) => setValue(x.target.value)} required />
            <select value={unit} onChange={(x) => setUnit(x.target.value as ClientProps["consumption_unit"])}><option value="L/s">L/s</option><option value="m3/mes">m³/mes</option></select>
          </div>
        </label>
        {unit === "m3/mes" && v !== null && <p className="muted small">= {fmt(toLps(v, unit), 4)} L/s</p>}
        <label className="field"><span>Estado <Help text="Los proyectados no suman demanda salvo que se active «incluir clientes proyectados» en el proyecto." /></span>
          <select value={status} onChange={(x) => setStatus(x.target.value as ClientProps["status"])}><option value="activo">Activo</option><option value="proyectado">Proyectado</option></select>
        </label>
        <fieldset>
          <legend>Conexión</legend>
          <p className="muted small">Se proyecta sobre la tubería {link?.id} a {fmt(pr.distanceM, 1)} m del punto.</p>
          <label className="radio-row"><input type="radio" checked={mode === "nearest"} disabled={!near} onChange={() => setMode("nearest")} />
            <span>Al nudo más cercano{near ? <>: <b>{net.nodes[near.node].id}</b> (a {fmt(near.distanceM, 1)} m del punto de conexión)</> : " (no hay nudos de consumo)"}</span></label>
          <label className="radio-row"><input type="radio" checked={mode === "new_node"} onChange={() => setMode("new_node")} />
            <span>A un nudo nuevo en el punto de conexión (divide la tubería {link?.id})</span></label>
          {mode === "new_node" && (
            <label className={`field ${e === null ? "invalid" : ""}`}><span>Cota del terreno <Help text="Cota del nudo nuevo. Es obligatoria: no se supone." /></span>
              <div className="with-unit"><input inputMode="decimal" value={elev} onChange={(x) => setElev(x.target.value)} placeholder={interp != null ? `interpolada ${fmt(interp, 2)}` : ""} /><em>m</em></div>
            </label>)}
          {mode === "new_node" && interp != null && e === null && (
            <button type="button" className="ghost small" onClick={() => setElev(fmt(interp, 2))}>Usar la interpolada entre extremos ({fmt(interp, 2)} m)</button>)}
        </fieldset>
        <div className="modal-actions"><button type="button" className="ghost" onClick={close}>Cancelar</button><button className="primary" disabled={!valid}>Agregar cliente</button></div>
      </form>
    </Modal>
  );
}
