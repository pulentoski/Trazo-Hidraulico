// Ajustes → Plataforma → Mapa base: proveedor (automático, Google Maps u OpenStreetMap) y estado de la key de Google Maps
// para todos; el superadministrador elige el proveedor y gestiona la key (cifrada en la base). El editor lo aplica
// sin reconstruir contenedores. Sin key de Google, el mapa base es OpenStreetMap.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { MapsStatus } from "../api/types";
import { fmtDate } from "../lib/format";
import type { MapProvider } from "../lib/mapConfig";
import { baseOf, testMapsKey, useMapConfig } from "../lib/mapConfig";
import { useAuth } from "../state/auth";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Icon } from "./Icons";

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
      await after(await api.saveMaps(body), cfg.provider === "osm" ? "Key guardada (el proveedor elegido sigue siendo OpenStreetMap)." : "Mapa base guardado: el editor ya usa Google Maps.");
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!window.confirm("¿Borrar la key y el Map ID guardados? El editor usará OpenStreetMap (o la key del respaldo).")) return;
    setBusy(true);
    try { await after(await api.deleteMaps(), "Key borrada."); } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const setProvider = async (provider: MapProvider) => {
    setBusy(true);
    try {
      const st = await api.saveMaps({ provider });
      setStatus(st);
      await cfg.load();
      const eff = baseOf(provider, useMapConfig.getState().apiKey);
      toast(`Proveedor guardado: el editor usa ${eff === "google" ? "Google Maps" : "OpenStreetMap"}.`);
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const probe = async () => {
    setTest(null);
    const k = key.trim() || (cfg.source === "db" ? cfg.apiKey : "");
    if (!k) return toast("Escriba una key para probarla.", "error");
    setBusy(true);
    setTest(await testMapsKey(k));
    setBusy(false);
  };

  const effective = baseOf(cfg.provider, cfg.apiKey);
  const hasKey = !!cfg.apiKey;
  const chosen: MapProvider = (status?.provider as MapProvider | undefined) ?? cfg.provider;
  const why = {
    auto: hasKey ? "Automático: hay key de Google guardada, se usa Google Maps." : "Automático: no hay key de Google, se usa OpenStreetMap.",
    google: hasKey ? "Google Maps, elegido en la plataforma." : "Google Maps elegido, pero no hay key: se usa OpenStreetMap.",
    osm: "OpenStreetMap, elegido en la plataforma (sin key ni costo).",
  }[cfg.provider];
  const keyHint = superadmin ? status?.key_hint ?? null : hasKey ? `…${cfg.apiKey.slice(-4)}` : null;
  const keySource = cfg.source === "db" ? "guardada en esta pantalla (cifrada)" : cfg.source === "build" ? "del servidor (VITE_GOOGLE_MAPS_API_KEY)" : "";
  const CARDS: [MapProvider, string, string][] = [
    ["auto", "Automático", "Google Maps si hay key guardada; si no, OpenStreetMap."],
    ["google", "Google Maps", "Calles, satélite e híbrido de Google. Requiere una key."],
    ["osm", "OpenStreetMap", "Sin key ni costo: calles de OSM y satélite de Esri, con búsqueda de direcciones Nominatim."],
  ];

  return (
    <section className="mapbase" aria-label="Proveedor y key del mapa base">
      <div className="in-use" aria-label="En uso ahora">
        <p className="in-use-title">En uso ahora</p>
        {!cfg.loaded ? <span className="skel skel-line w70" /> : (<>
          <p className="in-use-main">
            <span className={`provider-badge ${effective}`}><Icon.layers />{effective === "google" ? "Google Maps" : "OpenStreetMap"}</span>
            <span className="in-use-why">{why}</span>
          </p>
          <dl className="kv compact">
            <dt>Key guardada</dt><dd className="mono">{keyHint ?? "—"}</dd>
            <dt>Estado de la key</dt><dd>{hasKey ? <span className="ok-text">● Configurada{keySource ? ` · ${keySource}` : ""}</span> : <span className="muted">● Sin key</span>}</dd>
            {superadmin && <><dt>Última modificación</dt><dd>{status?.updated_at ? `${fmtDate(status.updated_at)}${status.updated_by ? ` · ${status.updated_by}` : ""}` : "—"}</dd></>}
            <dt>Map ID</dt><dd>{cfg.mapId ? <span className="mono">{cfg.mapId}</span> : <span className="muted">No configurado (tema oscuro del mapa de Google no disponible)</span>}</dd>
          </dl>
        </>)}
      </div>
      {!superadmin && <p className="muted small">La key es única para toda la plataforma y solo la gestiona el superadministrador. Por seguridad no se muestra completa.</p>}
      {superadmin && status && (
        <div className="maps-admin">
          <h3>Administración de la plataforma</h3>
          <fieldset className="choice-cards" aria-label="Proveedor del mapa base" disabled={busy}>
            <legend>Proveedor del mapa base</legend>
            {CARDS.map(([v, label, help]) => {
              const on = chosen === v;
              const unmet = v === "google" && !hasKey;
              return (
                <label key={v} className={`choice-card ${on ? "on" : ""} ${unmet ? "unmet" : ""}`}>
                  <span className="choice-head">
                    <input type="radio" name="map-provider" value={v} checked={on} onChange={() => void setProvider(v)} />
                    <b>{label}</b>
                    {on && <span className="chip-selected"><Icon.check />Seleccionado</span>}
                  </span>
                  <span className="choice-text">{help}</span>
                  {unmet && <span className="choice-warn"><Icon.alert />Sin key guardada: mientras tanto se usa OpenStreetMap.</span>}
                </label>
              );
            })}
          </fieldset>
          {!status.encryption_ready && <p className="notice warn small">Falta <code>SETTINGS_SECRET_KEY</code> en el .env del servidor: sin ella no se puede guardar la key cifrada (<code>make env</code> la agrega).</p>}
          {status.unreadable && <p className="notice warn small">Hay una key guardada que no se puede leer (cambió <code>SETTINGS_SECRET_KEY</code>): vuelva a ingresarla.</p>}
          <h3>Key de Google Maps</h3>
          <div className="form-grid">
            <label className="field stacked"><span>{status.configured ? "Reemplazar la key (vacío = conservar la actual)" : "API key de Google Maps"}</span>
              <input type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => { setKey(e.target.value); setTest(null); }}
                placeholder="AIza…" aria-label="API key de Google Maps" /></label>
            <label className="field stacked"><span>Map ID (opcional, para el tema oscuro del mapa)</span>
              <input value={mapId} onChange={(e) => setMapId(e.target.value)} placeholder="Ej.: 8e0a97af9386fef" aria-label="Map ID" /></label>
          </div>
          {test && <p className={`small ${test.ok ? "ok-text" : "bad-text"}`} role="status">{test.message}</p>}
          <div className="action-bar">
            {status.configured && <button className="danger-outline" disabled={busy} onClick={() => void remove()} title="Borra la key y el Map ID (pide confirmación)"><Icon.trash /><span>Borrar</span></button>}
            <span className="spacer" />
            <button disabled={busy} onClick={() => void probe()} title="Consulta Geocoding desde este navegador con la key"><Icon.activity /><span>Probar</span></button>
            <button className="primary" disabled={busy || !status.encryption_ready} onClick={() => void save()}><Icon.save /><span>Guardar</span></button>
          </div>
          <p className="muted small">Se guarda cifrada en la base de datos y nunca se muestra completa. Restrinja la key por
            referente HTTP al dominio publicado y solo a las APIs Maps JavaScript y Geocoding. «Probar» consulta Geocoding
            desde este navegador, con el mismo referente que usará el mapa.</p>
        </div>
      )}
    </section>
  );
}
