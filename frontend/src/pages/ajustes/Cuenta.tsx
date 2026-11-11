// Ajustes → Mi cuenta: perfil, seguridad (contraseña, segundo factor, sesiones) y preferencias de visualización.
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { api } from "../../api/client";
import type { MfaSetup, SessionOut } from "../../api/types";
import { PATHS } from "../../paths";
import { ROLE_LABEL, useAuth } from "../../state/auth";
import { errorText } from "../../state/projects";
import type { MapType, ThemePref } from "../../state/store";
import { useEditor, writePref } from "../../state/store";
import { Panel, SaveButton } from "./common";

const UNITS: [string, string, string][] = [
  ["Caudal y demanda", "L/s", "litros por segundo (EPANET UNITS LPS)"],
  ["Presión, cota, nivel y largo", "m", "metros de columna de agua / metros"],
  ["Diámetro y rugosidad D-W", "mm", "diámetro interior y ε en milímetros"],
  ["Velocidad", "m/s", ""],
  ["Pérdida unitaria", "m/km", "pérdida de carga por kilómetro de tubería"],
  ["Volumen", "m³", ""],
];

export function Perfil() {
  const { me, refresh } = useAuth();
  const [name, setName] = useState(me?.name ?? "");
  useEffect(() => { setName(me?.name ?? ""); }, [me?.name]);
  if (!me) return null;
  return (
    <Panel id="perfil" title="Perfil" description="Su nombre visible y las organizaciones a las que pertenece.">
      <div className="form-grid">
        <label className="field stacked"><span>Nombre visible</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} aria-label="Nombre visible" /></label>
        <label className="field stacked"><span>Correo</span><input value={me.email} disabled aria-label="Correo" /></label>
      </div>
      <dl className="kv">
        <dt>Organizaciones</dt><dd>{me.orgs.map((o) => `${o.name} (${ROLE_LABEL[o.role]})`).join(" · ") || "—"}</dd>
        {me.is_superadmin && <><dt>Plataforma</dt><dd>Superadministrador</dd></>}
        <dt>Segundo factor</dt><dd>{me.mfa_enabled ? "Activo" : "No configurado"}</dd>
      </dl>
      <SaveButton dirty={name.trim() !== me.name && name.trim().length > 0} onSave={async () => { await api.updateMe(name.trim()); await refresh(); }} />
    </Panel>
  );
}

export function Seguridad() {
  const { me, refresh } = useAuth();
  const toast = useEditor((s) => s.toast);
  const [params] = useSearchParams();
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [code, setCode] = useState("");
  const [sessions, setSessions] = useState<SessionOut[]>([]);
  const load = useCallback(() => api.sessions().then(setSessions).catch(() => undefined), []);
  useEffect(() => { void load(); }, [load]);
  if (!me) return null;
  const run = async (f: () => Promise<unknown>, ok: string) => {
    try { await f(); toast(ok); await refresh(); } catch (e) { toast(errorText(e), "error"); }
  };
  return (
    <Panel id="seguridad" title="Seguridad" description="Contraseña, segundo factor (TOTP) y sesiones abiertas en otros equipos.">
      {(params.get("mfa") || me.mfa_setup_required) && !me.mfa_enabled && (
        <p className="notice warn">Su rol exige el segundo factor: configúrelo para continuar.</p>
      )}
      <h3>Contraseña</h3>
      <form className="form-grid" onSubmit={(e) => e.preventDefault()}>
        <label className="field stacked"><span>Contraseña actual</span><input type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} /></label>
        <label className="field stacked"><span>Contraseña nueva</span><input type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></label>
      </form>
      <SaveButton dirty={!!cur && !!pw} label="Guardar contraseña" onSave={async () => {
        await api.changePassword(cur, pw); setCur(""); setPw(""); void load(); toast("Contraseña actualizada: se cerraron sus otras sesiones.");
      }} />
      <h3>Segundo factor (TOTP)</h3>
      {me.mfa_enabled ? (<>
        <p className="ok-text">Activo.</p>
        <form className="form-grid" onSubmit={(e) => { e.preventDefault(); const f = e.currentTarget.elements.namedItem("pw") as HTMLInputElement; void run(() => api.mfaDisable(f.value), "Segundo factor desactivado."); }}>
          <label className="field stacked"><span>Contraseña para desactivarlo</span><input name="pw" type="password" required /></label>
          <div><button>Desactivar</button></div>
        </form>
      </>) : setup ? (
        <form className="mfa-setup" onSubmit={(e) => { e.preventDefault(); void run(async () => { await api.mfaEnable(code); setSetup(null); }, "Segundo factor activado."); }}>
          <p>Escanee el código con su aplicación (Google Authenticator, Microsoft Authenticator, FreeOTP…) o ingrese la clave a mano.</p>
          <div className="qr" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
          <p className="mono small">{setup.secret}</p>
          <label className="field stacked"><span>Código de 6 dígitos</span><input inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={(e) => setCode(e.target.value)} /></label>
          <button className="primary">Activar</button>
        </form>
      ) : <button className="primary" onClick={async () => { try { setSetup(await api.mfaSetup()); } catch (e) { toast(errorText(e), "error"); } }}>Configurar</button>}
      <h3>Sesiones activas</h3>
      <div className="table-scroll">
        <table className="tbl compact">
          <thead><tr><th>Dispositivo</th><th>IP</th><th>Última actividad</th><th /></tr></thead>
          <tbody>{sessions.map((s) => (
            <tr key={s.id}><td className="small">{s.current ? "Esta sesión · " : ""}{(s.user_agent ?? "").slice(0, 60)}</td><td>{s.ip ?? "—"}</td>
              <td>{new Date(s.last_seen_at).toLocaleString("es-CL")}</td>
              <td>{!s.current && <button className="small ghost" onClick={async () => { await api.closeSession(s.id); void load(); }}>Cerrar</button>}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <button onClick={async () => { await api.logoutAll(); window.location.assign(PATHS.login); }}>Cerrar todas las sesiones</button>
    </Panel>
  );
}

const MAP_TYPES: [MapType, string][] = [["roadmap", "Calle"], ["terrain", "Terreno"], ["satellite", "Satélite"], ["hybrid", "Híbrido"]];

export function Preferencias() {
  const st = useEditor();
  const [theme, setTheme] = useState<ThemePref>(st.themePref);
  const [anim, setAnim] = useState(st.animations);
  const [mapType, setMapType] = useState<MapType>(st.mapType);
  const dirty = theme !== st.themePref || anim !== st.animations || mapType !== st.mapType;
  const save = async () => {
    st.set({ themePref: theme, animations: anim, mapType });
    writePref("theme", theme);
    writePref("animations", anim);
    writePref("mapType", mapType);
  };
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  return (
    <Panel id="preferencias" title="Preferencias" description="Tema, animaciones y opciones de visualización de este navegador.">
      <h3>Tema</h3>
      <div className="seg plain" role="radiogroup" aria-label="Tema">
        {([["light", "Claro"], ["dark", "Oscuro"], ["system", "Según el sistema"]] as [ThemePref, string][]).map(([v, l]) => (
          <button key={v} role="radio" aria-checked={theme === v} className={theme === v ? "on" : ""} onClick={() => setTheme(v)}>{l}</button>
        ))}
      </div>
      <h3>Animaciones</h3>
      <label className="switch-row">
        <input type="checkbox" role="switch" checked={anim} onChange={(e) => setAnim(e.target.checked)} aria-label="Animaciones" />
        <span>Animaciones de la interfaz y del mapa (transiciones, flujo en tuberías, pulso de alertas, reproducir día)</span>
      </label>
      {reduced && <p className="muted small">Su sistema pide reducir el movimiento: las animaciones quedan desactivadas igual.</p>}
      <h3>Mapa</h3>
      <label className="field"><span>Tipo de mapa por defecto</span>
        <select value={mapType} onChange={(e) => setMapType(e.target.value as MapType)} aria-label="Tipo de mapa por defecto">
          {MAP_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <h3>Unidades</h3>
      <p className="muted small">El modelo trabaja en el sistema internacional; los .inp importados en otras unidades se convierten al abrirlos.</p>
      <table className="tbl compact">
        <tbody>{UNITS.map(([what, u, note]) => <tr key={what}><td>{what}</td><td className="mono">{u}</td><td className="muted">{note}</td></tr>)}</tbody>
      </table>
      <SaveButton dirty={dirty} onSave={save} />
    </Panel>
  );
}
