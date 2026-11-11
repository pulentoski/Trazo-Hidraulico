// Operación de bombas y válvulas de control: horario por hora, control por nivel y curva de la bomba.
import type { ELink, LinkProps } from "../lib/network";
import { fmt } from "../lib/format";
import { useEditor } from "../state/store";
import { Help, NumField } from "./Fields";
import { Section } from "./Section";

function upd(uid: string, patch: Partial<LinkProps>) {
  useEditor.getState().commit((n) => ({ ...n, links: { ...n.links, [uid]: { ...n.links[uid], props: { ...n.links[uid].props, ...patch } } } }));
}

export function PumpOperation({ link }: { link: ELink }) {
  const { net } = useEditor();
  const p = link.props;
  const sched = p.schedule ?? null;
  const tanks = Object.values(net.nodes).filter((n) => n.kind === "tank");
  const lc = p.level_control ?? null;
  const pts = (p.curve_points ?? []) as [number, number][];
  const toggle = (h: number) => {
    const s = [...(sched ?? Array(24).fill(1))];
    s[h] = s[h] ? 0 : 1;
    upd(link.uid, { schedule: s });
  };
  const setPts = (next: [number, number][] | null) => upd(link.uid, { curve_points: next, ...(next ? { pump_power: null, pump_curve: null } : {}) });
  const hours = sched ? sched.reduce((a, b) => a + b, 0) : 24;
  return (
    <>
      <Section id="bomba.horario" title="Horario" extra={<Help text="Encendida (1) o apagada (0) en cada hora, como la columna F de SimulaEST1. Se repite cada día. En válvulas, «encendida» es su consigna." />}>
        <div className="sched">
          {Array.from({ length: 24 }, (_, h) => (
            <button key={h} className={`small ${!sched || sched[h] ? "on" : ""}`} onClick={() => toggle(h)} title={`${h}:00–${h + 1}:00`}>{h}</button>
          ))}
        </div>
        <div className="toolbar">
          <span className="muted small">{sched ? `${hours} h encendida` : "Sin horario (siempre según su estado)"}</span>
          {sched && <button className="small ghost" onClick={() => upd(link.uid, { schedule: null })}>Quitar horario</button>}
        </div>
      </Section>
      <Section id="bomba.control" title="Control por nivel">
        <label className="field"><span>Estanque</span>
          <select value={lc?.tank ?? ""} onChange={(e) => {
            const t = tanks.find((x) => x.id === e.target.value);
            upd(link.uid, { level_control: t ? { tank: t.id, on_below: lc?.on_below ?? Math.max(0, (t.props.max_level ?? 3) * 0.4),
              off_above: lc?.off_above ?? (t.props.max_level ?? 3) * 0.9 } : null });
          }}>
            <option value="">— sin control por nivel</option>{tanks.map((t) => <option key={t.uid} value={t.id}>{t.id}</option>)}
          </select></label>
        {lc && (<>
          <NumField label="Enciende bajo" unit="m" value={lc.on_below} onCommit={(v) => upd(link.uid, { level_control: { ...lc, on_below: v ?? lc.on_below } })} />
          <NumField label="Apaga sobre" unit="m" value={lc.off_above} onCommit={(v) => upd(link.uid, { level_control: { ...lc, off_above: v ?? lc.off_above } })} />
          {sched && <p className="muted small">Con horario: fuera de las horas encendidas queda apagada; dentro, el nivel la enciende y apaga.</p>}
        </>)}
      </Section>
      {link.kind === "pump" && (
        <Section id="bomba.curva" title="Curva de la bomba" extra={<Help text="Caudal (L/s) y altura (m): 1 punto de diseño o 3 puntos (caudal creciente, altura decreciente). Reemplaza a la potencia constante." />}>
          {pts.map(([q, h], i) => (
            <div className="grid2" key={i}>
              <NumField label={`Q${i + 1}`} unit="L/s" value={q} onCommit={(v) => setPts(pts.map((x, k) => (k === i ? [v ?? q, x[1]] : x)))} />
              <NumField label={`H${i + 1}`} unit="m" value={h} onCommit={(v) => setPts(pts.map((x, k) => (k === i ? [x[0], v ?? h] : x)))} />
            </div>
          ))}
          <div className="toolbar">
            <button className="small" onClick={() => setPts([[10, 60]])}>1 punto</button>
            <button className="small" onClick={() => {
              const [q, h] = pts[0] ?? [10, 60];
              setPts([[0, Math.round(h * 1.33)], [q, h], [Math.round(q * 2 * 10) / 10, Math.round(h * 0.5)]]);
            }}>3 puntos</button>
            {pts.length > 0 && <button className="small ghost" onClick={() => setPts(null)}>Quitar curva</button>}
            {!pts.length && p.pump_power ? <span className="muted small">Potencia constante {fmt(p.pump_power, 1)} kW</span> : null}
          </div>
        </Section>
      )}
    </>
  );
}
