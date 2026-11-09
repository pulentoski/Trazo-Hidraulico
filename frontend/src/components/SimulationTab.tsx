// Pestaña «Simulación»: período extendido (duración y pasos) y curvas de modulación horaria.
import { useState } from "react";
import { fmt, parseNum } from "../lib/format";
import { CURVA_MOD_NORMALIZADA, DEFAULT_PATTERN_ID, formatPatterns, mean, meanWarning, normalize, parsePatterns } from "../lib/patterns";
import { useEditor } from "../state/store";
import { Chart } from "./Chart";
import { Help, NumField } from "./Fields";

export function SimulationTab() {
  const { options, setOptions, aux, setAux, toast } = useEditor();
  const patterns = parsePatterns(aux.patterns);
  const ids = Object.keys(patterns);
  const [sel, setSel] = useState<string>(options.extra?.PATTERN ?? ids[0] ?? "");
  const current = patterns[sel];
  const eps = options.duration_h != null && options.duration_h > 0;
  const defaultPattern = options.extra?.PATTERN ?? "";

  const savePatterns = (next: Record<string, number[]>) => setAux({ ...aux, patterns: formatPatterns(next) });
  const setDefault = (id: string) => {
    const extra = { ...(options.extra ?? {}) };
    if (id) extra.PATTERN = id; else delete extra.PATTERN;
    setOptions({ ...options, extra });
  };
  const addDefault = () => {
    const id = patterns[DEFAULT_PATTERN_ID] ? `${DEFAULT_PATTERN_ID}${ids.length + 1}` : DEFAULT_PATTERN_ID;
    savePatterns({ ...patterns, [id]: CURVA_MOD_NORMALIZADA });
    setSel(id);
    if (!defaultPattern) setDefault(id);
    toast(`Curva ${id} creada desde CurvaMod normalizada (promedio 1).`);
  };
  const setValue = (h: number, v: number | null) => {
    if (v === null || !current) return;
    const vals = [...current];
    vals[h] = v;
    savePatterns({ ...patterns, [sel]: vals });
  };
  const warn = current ? meanWarning(current) : null;

  return (
    <div className="sim-tab">
      <section>
        <h4>Período extendido</h4>
        <label className="check"><input type="checkbox" checked={eps}
          onChange={(e) => setOptions({ ...options, duration_h: e.target.checked ? 24 : null })} />Simular en el tiempo (24 h)</label>
        {eps && (<div className="grid4">
          <NumField label="Duración" unit="h" value={options.duration_h} digits={1} onCommit={(v) => setOptions({ ...options, duration_h: Math.max(1, v ?? 24) })} />
          <NumField label="Paso hidráulico" unit="min" value={options.hydraulic_step_min ?? 60} digits={0}
            onCommit={(v) => setOptions({ ...options, hydraulic_step_min: Math.max(1, Math.round(v ?? 60)) })}
            hint="Con estanques que se llenan o vacían conviene un paso menor (p. ej. 5 min): EPANET revisa la entrada cerrada recién en el paso siguiente." />
          <NumField label="Paso de patrón" unit="min" value={options.pattern_step_min ?? 60} digits={0} onCommit={(v) => setOptions({ ...options, pattern_step_min: Math.max(1, Math.round(v ?? 60)) })} />
          <NumField label="Paso de reporte" unit="min" value={options.report_step_min ?? 60} digits={0} onCommit={(v) => setOptions({ ...options, report_step_min: Math.max(1, Math.round(v ?? 60)) })} />
        </div>)}
        {!eps && <p className="muted small">Sin período extendido se simula un instante (régimen permanente) con las demandas base.</p>}
        {(options.demand_multiplier ?? 1) !== 1 && <p className="small">Escenario de demanda activo: multiplicador {fmt(options.demand_multiplier ?? 1, 3)} (pestaña Demanda).</p>}
      </section>
      <section>
        <h4>Curvas de modulación horaria <Help text="Coeficientes que multiplican la demanda base de cada hora. El promedio debe ser 1 para que el volumen diario corresponda al caudal base; si no lo es se advierte y puede normalizarse. La curva por defecto se aplica a todas las demandas sin patrón propio." /></h4>
        <div className="toolbar">
          {ids.length > 0 && <select value={sel} onChange={(e) => setSel(e.target.value)} aria-label="Curva">{ids.map((i) => <option key={i}>{i}</option>)}</select>}
          <button className="small" onClick={addDefault}>+ Curva desde CurvaMod</button>
          <label className="field inline"><span>Por defecto</span>
            <select value={defaultPattern} onChange={(e) => setDefault(e.target.value)}>
              <option value="">— (sin modulación)</option>{ids.map((i) => <option key={i}>{i}</option>)}
            </select></label>
        </div>
        {current && (<>
          <div className="pattern-grid">
            {Array.from({ length: Math.max(24, current.length) }, (_, h) => (
              <label key={h}><span>{h} h</span>
                <input inputMode="decimal" defaultValue={String(current[h] ?? "").replace(".", ",")} key={`${sel}-${h}-${current[h]}`}
                  onBlur={(e) => setValue(h, parseNum(e.target.value))} /></label>
            ))}
          </div>
          <div className="toolbar">
            <span className={warn ? "warn-text" : "ok-text"}>Promedio {fmt(mean(current), 3)} · máx {fmt(Math.max(...current), 2)} · mín {fmt(Math.min(...current), 2)}</span>
            {warn && <><span className="warn-text small">{warn}</span><button className="small" onClick={() => savePatterns({ ...patterns, [sel]: normalize(current) })}>Normalizar</button></>}
            <button className="small ghost" onClick={() => { const n = { ...patterns }; delete n[sel]; savePatterns(n); if (defaultPattern === sel) setDefault(""); setSel(Object.keys(n)[0] ?? ""); }}>Eliminar curva</button>
          </div>
          <Chart title={`Curva ${sel}`} x={current.map((_, i) => i)} xLabel="Hora" xFormat={(v) => `${v}`} yLabel="Coeficiente" step
            series={[{ name: sel, values: current }]} refLines={[{ value: 1, label: "Promedio 1", color: "#5f6f7f" }]} fileName={`curva-${sel}`} height={200} />
        </>)}
      </section>
    </div>
  );
}
