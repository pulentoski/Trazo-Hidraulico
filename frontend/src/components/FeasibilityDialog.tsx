// Factibilidad de un nuevo cliente: simula la red con el cliente agregado temporalmente (no modifica el proyecto).
import { useMemo, useState } from "react";
import { api } from "../api/client";
import type { FeasibilityRequest, FeasibilityResult } from "../api/types";
import { fmt, parseNum } from "../lib/format";
import type { EClient, Network } from "../lib/network";
import { applyUpgrade, interpolatedElevation, nextId, projectOnLink, splitPipe, uid } from "../lib/network";
import { flushPending } from "../state/live";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Modal } from "./Dialogs";
import { Help } from "./Fields";

export function FeasibilityDialog() {
  const draft = useEditor((s) => s.feasibilityDraft);
  if (!draft) return null;
  return <FeasibilityForm key={`${draft.pos[0]},${draft.pos[1]}`} pos={draft.pos} linkUid={draft.link} />;
}

function FeasibilityForm({ pos, linkUid }: { pos: [number, number]; linkUid: string }) {
  const { net, project, set, toast, commit, select } = useEditor();
  const link = net.links[linkUid];
  const pr = useMemo(() => projectOnLink(net, linkUid, pos), [net, linkUid, pos]);
  const interp = interpolatedElevation(net, pr);
  const [q, setQ] = useState("");
  const [elev, setElev] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<FeasibilityResult | null>(null);
  const [req, setReq] = useState<FeasibilityRequest | null>(null);
  /** Ir al elemento de una fila de resultados (cliente o tramo, por su ID). */
  const go = (pool: "clients" | "links", id: string) => {
    const hit = Object.values(net[pool]).find((x) => x.id === id);
    if (hit) useEditor.getState().focus([hit.uid]);
  };
  const close = () => set({ feasibilityDraft: null });
  const qv = parseNum(q);
  const ev = parseNum(elev);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!project || qv === null || qv <= 0 || ev === null || !link) return;
    setBusy(true);
    try {
      if (!(await flushPending())) throw new Error("No se pudieron guardar los cambios pendientes.");
      const version = useEditor.getState().serverVersion!;
      const body: FeasibilityRequest = { model_version: version, link: link.id, point: [pos[0], pos[1]], consumption_lps: qv,
        elevation: ev, name: name.trim() || null };
      setRes(await api.feasibility(project.id, body));
      setReq(body);
    } catch (err) {
      toast(errorText(err), "error");
    } finally {
      setBusy(false);
    }
  };

  const openReport = async () => {
    if (!project || !req) return;
    const win = window.open("", "_blank");
    try {
      const html = await api.feasibilityReport(project.id, req);
      const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
      if (win) win.location.href = url;
      else window.location.assign(url);
    } catch (err) {
      win?.close();
      toast(errorText(err), "error");
    }
  };

  const addClient = (withUpgrade = false) => {
    if (!res || !req) return;
    const id = nextId(Object.values(net.clients).map((c) => c.id), "client");
    const upgrade = withUpgrade ? res.upgrades.find((u) => u.feasible) : undefined;
    let changed: string[] = [];
    commit((n) => {
      const r = splitPipe(n, projectOnLink(n, linkUid, pos), nextId(Object.values(n.nodes).map((x) => x.id), "junction"), req.elevation);
      const c: EClient = { uid: uid(), id, pos, node: r.node, link: linkUid, connection: pr.point, props: {
        name: req.name ?? null, client_type: "residencial", status: "activo", consumption_value: req.consumption_lps,
        consumption_unit: "L/s", connection_mode: "new_node", elevation: req.elevation, attributes: {} } };
      let next: Network = { ...r.net, clients: { ...r.net.clients, [c.uid]: c } };
      if (upgrade) {
        // Si el cuello de botella es la tubería que se dividió, la mejora va a ambas partes.
        const up = applyUpgrade(next, upgrade, useEditor.getState().catalog, upgrade.link === link?.id ? r.second : null);
        next = up.net;
        changed = up.changed;
      }
      return next;
    });
    if (upgrade) toast(`Mejora aplicada: ${[...new Set(changed)].join(", ")} a DN ${upgrade.dn_to}.`);
    const created = Object.values(useEditor.getState().net.clients).find((c) => c.id === id);
    if (created) select([created.uid]);
    toast(`Cliente ${id} agregado al proyecto (nudo nuevo en ${link?.id}).`);
    close();
  };

  const pmin = res?.criteria.find((c) => c.key === "pressure_min");
  return (
    <Modal title="Factibilidad de un nuevo cliente" onClose={close} wide>
      <form onSubmit={run} className="analysis-grid">
        <div>
          <p className="muted small">Conexión sobre la tubería <b>{link?.id}</b> ({link?.props.material ?? "—"} DN {link?.props.dn ?? "—"}),
            a {fmt(pr.fraction * 100, 0)} % de su largo. El proyecto no se modifica.</p>
          <label className="field"><span>Consumo</span><div className="with-unit"><input autoFocus inputMode="decimal" value={q} onChange={(x) => setQ(x.target.value)} /><em>L/s</em></div></label>
          <label className={`field ${elev && ev === null ? "invalid" : ""}`}><span>Cota del terreno <Help text="Cota del punto de conexión del nuevo cliente. Obligatoria." /></span>
            <div className="with-unit"><input inputMode="decimal" value={elev} onChange={(x) => setElev(x.target.value)} placeholder={interp != null ? `interpolada ${fmt(interp, 2)}` : ""} /><em>m</em></div>
          </label>
          {interp != null && ev === null && <button type="button" className="ghost small" onClick={() => setElev(fmt(interp, 2))}>Usar la interpolada ({fmt(interp, 2)} m)</button>}
          <label className="field"><span>Nombre (opcional)</span><input value={name} onChange={(x) => setName(x.target.value)} /></label>
          <div className="modal-actions"><button className="primary" disabled={busy || qv === null || qv <= 0 || ev === null}>{busy ? "Simulando…" : "Evaluar factibilidad"}</button></div>
        </div>
        <div>
          {!res ? <p className="muted">Ingrese el consumo y la cota y presione «Evaluar». Se simula la red completa con OWA-EPANET.</p> : (
            <>
              <span className={`verdict ${res.feasible ? "ok" : "bad"}`}>{res.verdict}</span>
              <dl className="kv compact" style={{ marginTop: 10 }}>
                <dt>Presión en el punto</dt><dd><b>{fmt(res.pressure_new, 2)} m.c.a.</b></dd>
                <dt>Mínimo exigido</dt><dd>{fmt(pmin?.value, 1)} m.c.a. {pmin && !pmin.verified && <span className="badge warn">no verificado</span>}</dd>
                <dt>Margen</dt><dd className={res.margin != null && res.margin < 0 ? "bad-text" : "ok-text"}>{fmt(res.margin, 2)} m</dd>
                <dt>Análisis</dt><dd>{res.analysis} · v{res.model_version}</dd>
              </dl>
              {res.reasons.map((r, i) => <p key={i} className="issue-line error">{r}</p>)}
            </>
          )}
        </div>
      </form>
      {res && (
        <>
          {res.affected_clients.length > 0 && (<>
            <h3>Consumos bajo la presión mínima</h3>
            <table className="tbl compact"><thead><tr><th>ID</th><th>Nombre</th><th>Nudo</th><th className="num">Antes (m)</th><th className="num">Después (m)</th><th>Causado</th></tr></thead>
              <tbody>{res.affected_clients.map((a) => <tr key={a.id} className="clickable" title="Ir al cliente" onClick={() => go("clients", a.id)}><td>{a.id}</td><td>{a.name ?? ""}</td><td>{a.node}</td><td className="num">{fmt(a.before, 2)}</td><td className="num bad">{fmt(a.after, 2)}</td><td>{a.newly_below ? "sí" : "ya estaba bajo"}</td></tr>)}</tbody></table>
          </>)}
          {res.link_issues.length > 0 && (<>
            <h3>Tramos sobre la velocidad o pérdida máxima</h3>
            <table className="tbl compact"><thead><tr><th>Tramo</th><th className="num">DN</th><th className="num">Velocidad (m/s)</th><th className="num">Pérdida (m/km)</th></tr></thead>
              <tbody>{res.link_issues.map((i) => <tr key={i.id} className="clickable" title="Ir al tramo" onClick={() => go("links", i.id)}><td>{i.id}</td><td className="num">{i.dn ?? "—"}</td>
                <td className={`num ${i.over_velocity ? "bad" : ""}`}>{fmt(i.velocity_before, 2)} → {fmt(i.velocity_after, 2)}</td>
                <td className={`num ${i.over_headloss ? "bad" : ""}`}>{fmt(i.headloss_before, 1)} → {fmt(i.headloss_after, 1)}</td></tr>)}</tbody></table>
          </>)}
          {res.upgrades.length > 0 && (<>
            <h3>Cuello de botella: {res.bottleneck} — {res.upgrade_feasible ? "pasa a FACTIBLE aumentando el DN" : "aumentar el DN no basta"}</h3>
            <table className="tbl compact"><thead><tr><th>Tramo</th><th>Material</th><th className="num">DN</th><th className="num">Interior (mm)</th><th className="num">Presión punto (m)</th><th>Resultado</th></tr></thead>
              <tbody>{res.upgrades.map((u, i) => <tr key={i} className="clickable" title="Ir al tramo" onClick={() => go("links", u.link)}><td>{u.link}</td><td>{u.material ?? "—"} {u.pipe_class ?? ""}</td><td className="num">{u.dn_from ?? "—"} → {u.dn_to ?? "—"}</td>
                <td className="num">{fmt(u.inner_from, 1)} → {fmt(u.inner_to, 1)}</td><td className="num">{fmt(u.pressure_new, 2)}</td><td>{u.feasible ? "FACTIBLE" : u.note ?? "no factible"}</td></tr>)}</tbody></table>
          </>)}
          <div className="modal-actions">
            <button type="button" onClick={() => void openReport()}>Informe (imprimir / PDF)</button>
            {res.upgrade_feasible && res.upgrades.some((u) => u.feasible) && (
              <button type="button" className="primary" onClick={() => addClient(true)}
                title="Agrega el cliente y cambia el tramo cuello de botella al DN sugerido (catálogo)">
                Agregar cliente y aplicar mejora (DN {res.upgrades.find((u) => u.feasible)?.dn_to})</button>
            )}
            <button type="button" className={res.feasible ? "primary" : ""} disabled={!res.feasible} onClick={() => addClient(false)}
              title={res.feasible ? "Agrega el cliente con un nudo nuevo en el punto de conexión" : "Solo disponible si es factible"}>Agregar cliente al proyecto</button>
          </div>
        </>
      )}
    </Modal>
  );
}
