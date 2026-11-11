// Configuración → Mapa base: estado de la key de Google Maps para todos; el superadministrador la ingresa, prueba
// y borra. Se guarda cifrada en la base y el mapa se activa sin reconstruir contenedores.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { MapsStatus } from "../api/types";
import { fmtDate } from "../lib/format";
import { testMapsKey, useMapConfig } from "../lib/mapConfig";
import { useAuth } from "../state/auth";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";

export function MapBaseSection() {
  const me = useAuth((s) => s.me);
  const toast = useEditor((s) => s.toast);
  const cfg = useMapConfig();
  const [status, setStatus] = useState<MapsStatus | null>(null);
  const [key, setKey] = useState("");
  const [mapId, setMapId] = useState("");
  const [busy, setBusy] = useState(false);
  const [test, setTest] = useState<{ ok: boolean; message: string } | null>(null);
  const superadmin = !!me?.is_superadmin;

  useEffect(() => { void cfg.load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!superadmin) return;
    api.mapsStatus().then((s) => { setStatus(s); setMapId(s.map_id ?? ""); }).catch((e) => toast(errorText(e), "error"));
  }, [superadmin, toast]);

  const hadGoogle = typeof window !== "undefined" && "google" in window;
  const after = async (s: MapsStatus, msg: string) => {
    setStatus(s);
    setKey("");
    const before = useMapConfig.getState().apiKey;
    await cfg.load();
    const now = useMapConfig.getState().apiKey;
    toast(hadGoogle && before && now !== before ? `${msg} Recargue la página para usar la key nueva en el mapa.` : msg);
  };
  const save = async () => {
    setBusy(true);
    try {
      const body: { api_key?: string; map_id?: string } = { map_id: mapId };
      if (key.trim()) body.api_key = key.trim();
      await after(await api.saveMaps(body), "Mapa base guardado: el editor ya usa Google Maps.");
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!window.confirm("¿Borrar la key y el Map ID guardados? El editor volverá al lienzo neutro (o a la key del respaldo).")) return;
    setBusy(true);
    try { await after(await api.deleteMaps(), "Key borrada."); } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const probe = async () => {
    setTest(null);
    const k = key.trim() || (cfg.source === "db" ? cfg.apiKey : "");
    if (!k) return toast("Escriba una key para probarla.", "error");
    setBusy(true);
    setTest(await testMapsKey(k));
    setBusy(false);
  };

  const state = cfg.source === "db" ? <span className="ok-text">● Configurada desde esta pantalla</span>
    : cfg.source === "build" ? <span className="ok-text">● Configurada en el servidor (respaldo VITE_GOOGLE_MAPS_API_KEY)</span>
      : <span className="warn-text">● Sin key: el editor usa un lienzo neutro</span>;

  return (
    <section className="card" aria-label="Mapa base">
      <h2>Mapa base</h2>
      <dl className="kv">
        <dt>Google Maps</dt><dd>{cfg.loaded ? state : "…"}</dd>
        <dt>Map ID (estilo vectorial)</dt><dd>{cfg.mapId ? "Configurado" : "No configurado (tema oscuro del mapa no disponible)"}</dd>
      </dl>
      {!superadmin && <p className="muted small">La key es única para toda la plataforma y solo la gestiona el superadministrador. Por seguridad no se muestra.</p>}
      {superadmin && status && (
        <div className="maps-admin">
          <h3>Administración de la plataforma</h3>
          {!status.encryption_ready && <p className="notice warn small">Falta <code>SETTINGS_SECRET_KEY</code> en el .env del servidor: sin ella no se puede guardar la key cifrada (<code>make env</code> la agrega).</p>}
          {status.unreadable && <p className="notice warn small">Hay una key guardada que no se puede leer (cambió <code>SETTINGS_SECRET_KEY</code>): vuelva a ingresarla.</p>}
          <dl className="kv compact">
            <dt>Key guardada</dt><dd className="mono">{status.key_hint ?? "—"}</dd>
            <dt>Última modificación</dt><dd>{status.updated_at ? `${fmtDate(status.updated_at)}${status.updated_by ? ` · ${status.updated_by}` : ""}` : "—"}</dd>
          </dl>
          <label className="field stacked"><span>{status.configured ? "Reemplazar la key (vacío = conservar la actual)" : "API key de Google Maps"}</span>
            <input type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => { setKey(e.target.value); setTest(null); }}
              placeholder="AIza…" aria-label="API key de Google Maps" /></label>
          <label className="field stacked"><span>Map ID (opcional, para el tema oscuro del mapa)</span>
            <input value={mapId} onChange={(e) => setMapId(e.target.value)} placeholder="Ej.: 8e0a97af9386fef" aria-label="Map ID" /></label>
          {test && <p className={`small ${test.ok ? "ok-text" : "bad-text"}`} role="status">{test.message}</p>}
          <div className="modal-actions left">
            <button disabled={busy} onClick={() => void probe()}>Probar</button>
            <button className="primary" disabled={busy || !status.encryption_ready} onClick={() => void save()}>Guardar</button>
            {status.configured && <button className="ghost danger-text" disabled={busy} onClick={() => void remove()}>Borrar</button>}
          </div>
          <p className="muted small">Se guarda cifrada en la base de datos y nunca se muestra completa. Restrinja la key por
            referente HTTP al dominio publicado y solo a las APIs Maps JavaScript y Geocoding. «Probar» consulta Geocoding
            desde este navegador, con el mismo referente que usará el mapa.</p>
        </div>
      )}
    </section>
  );
}
