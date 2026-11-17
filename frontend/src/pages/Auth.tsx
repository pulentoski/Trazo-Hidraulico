// Pantallas públicas (estilo v2, docs/referencias/estilo/login.html): ingreso con segundo factor, recuperación de
// contraseña e invitación. Tarjeta a la izquierda, escena del ciclo del agua a la derecha, tema y pausa arriba a la
// derecha y la versión al pie. Conectadas a la API real (401, 423, 429, TOTP, enlaces de un solo uso).
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api, ApiError } from "../api/client";
import type { InvitationInfo } from "../api/types";
import { Icon } from "../components/Icons";
import { Logo } from "../components/PageHeader";
import { Scene } from "../components/Scene";
import { LOGIN_SCENE, LOGIN_SCENE_VIEWBOX } from "../components/scenes/loginScene";
import { useEditor, writePref } from "../state/store";
import { PATHS } from "../paths";
import { ROLE_LABEL, useAuth } from "../state/auth";
import { errorText } from "../state/projects";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  const theme = useEditor((s) => s.theme);
  const set = useEditor((s) => s.set);
  const [paused, setPaused] = useState(false);
  const next = theme === "dark" ? "light" : "dark";
  return (
    <div className="auth-page">
      <div className="auth-tools">
        <button className="ib" onClick={() => setPaused(!paused)} aria-pressed={paused} title={paused ? "Reanudar la animación" : "Pausar la animación"}
          aria-label={paused ? "Reanudar la animación" : "Pausar la animación"}>{paused ? <Icon.resume /> : <Icon.pause />}</button>
        <button className="ib" onClick={() => { set({ themePref: next, theme: next }); writePref("theme", next); }}
          title="Cambiar tema claro / oscuro" aria-label="Cambiar tema claro u oscuro">{theme === "dark" ? <Icon.sun /> : <Icon.moon />}</button>
      </div>
      <div className="auth-scene" aria-hidden="true">
        <Scene svg={LOGIN_SCENE} viewBox={LOGIN_SCENE_VIEWBOX} paused={paused} />
      </div>
      <main className="auth-card">
        <div className="auth-brand"><Logo size={44} /><b><span>Trazo</span> Hidráulico</b></div>
        <p className="auth-tagline">Diseño, simulación y gestión de redes de agua potable</p>
        <h1>{title}</h1>
        {children}
      </main>
      <footer className="auth-foot">Trazo Hidráulico • versión {__APP_VERSION__}</footer>
    </div>
  );
}

/** Campo de contraseña con botón para mostrarla u ocultarla (maqueta de ingreso). */
function PasswordInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const [shown, setShown] = useState(false);
  return (
    <span className="pw-field">
      <input {...props} type={shown ? "text" : "password"} />
      <button type="button" className="eye" onClick={() => setShown(!shown)} aria-pressed={shown}
        title="Mostrar u ocultar contraseña" aria-label="Mostrar u ocultar contraseña">{shown ? <Icon.eyeOff /> : <Icon.eye />}</button>
    </span>
  );
}

function safeNext(v: string | null): string {
  return v && v.startsWith("/") && !v.startsWith("//") ? v : PATHS.home;
}

/** Mensajes claros para cada respuesta del ingreso (nunca dejar el formulario «pegado»). */
export function loginErrorText(err: unknown): string {
  if (err instanceof TypeError) return "No se pudo contactar al servidor. Revise su conexión y que la dirección sea la correcta.";
  const status = err instanceof ApiError ? err.status : 0;
  const code = err instanceof ApiError && err.body && typeof err.body === "object" && "code" in err.body
    ? (err.body as { code: unknown }).code : null;
  const msg = errorText(err);
  if (status === 423) return `${msg} Para desbloquearla antes, quien administra el servidor puede ejecutar make unlock-user.`;
  if (status === 401 && code === "bad_credentials") return msg;
  if (status === 401 && (code === "login_required" || code === "mfa_pending")) return "La sesión no se mantuvo: vuelva a ingresar con su correo y contraseña.";
  if (status === 401 && code === "bad_code") return "Código incorrecto. Use el código actual de su aplicación de autenticación (cambia cada 30 s).";
  if (status === 429) return msg || "Demasiados intentos: espere un minuto.";
  if (status >= 500) return "El servidor no respondió correctamente. Intente en unos minutos.";
  return msg;
}

export function Login() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const refresh = useAuth((s) => s.refresh);
  const [step, setStep] = useState<"password" | "mfa">("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.me().then((me) => { if (me.mfa_pending) setStep("mfa"); else navigate(safeNext(params.get("volver")), { replace: true }); })
      .catch(() => undefined);
  }, [navigate, params]);
  const done = async (): Promise<boolean> => {
    const me = await refresh();
    if (!me || me.mfa_pending) {
      // El servidor aceptó el ingreso, pero el navegador no devolvió la cookie de sesión.
      setStep("password");
      setError(window.location.protocol === "http:"
        ? "El ingreso fue aceptado, pero el navegador no guardó la sesión: este sitio se abrió por http:// y la "
          + "cookie de sesión exige HTTPS. Entre por https:// o, solo para pruebas, configure COOKIE_SECURE=false en el servidor."
        : "El ingreso fue aceptado, pero el navegador no guardó la cookie de sesión. Permita las cookies de este sitio "
          + "(no use bloqueo de cookies propias) y vuelva a intentarlo.");
      return false;
    }
    navigate(me.mfa_setup_required ? `${PATHS.ajustes("seguridad")}?mfa=1` : safeNext(params.get("volver")), { replace: true });
    return true;
  };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (step === "password") {
        const r = await api.login(email, password);
        if (r.mfa_required) setStep("mfa");
        else await done();
      } else {
        await api.mfa(code);
        await done();
      }
    } catch (err) { setError(loginErrorText(err)); } finally { setBusy(false); }
  };
  return (
    <Card title={step === "password" ? "Ingresar" : "Segundo factor"}>
      <form onSubmit={submit} className="auth-form">
        {step === "password" ? (<>
          <label className="field stacked"><span>Correo</span>
            <input type="email" autoComplete="username" inputMode="email" autoFocus required placeholder="correo@ejemplo.cl" value={email}
              aria-invalid={!!error} className={error ? "bad" : ""} onChange={(e) => setEmail(e.target.value)} /></label>
          <label className="field stacked"><span>Contraseña</span>
            <PasswordInput autoComplete="current-password" required placeholder="••••••••" value={password} aria-invalid={!!error}
              className={error ? "bad" : ""} onChange={(e) => setPassword(e.target.value)} /></label>
        </>) : (
          <label className="field stacked"><span>Código de 6 dígitos de su aplicación de autenticación</span>
            <input inputMode="numeric" autoComplete="one-time-code" autoFocus required pattern="[0-9 ]{6,8}" value={code} onChange={(e) => setCode(e.target.value)} /></label>
        )}
        {error && <p className="field-error" role="alert">{error}</p>}
        <button className={`primary auth-submit ${busy ? "loading" : ""}`} disabled={busy}>
          {busy && <span className="spin" aria-hidden="true" />}{busy ? (step === "password" ? "Ingresando…" : "Verificando…") : step === "password" ? "Ingresar" : "Verificar"}</button>
        {step === "password" ? <Link className="forgot" to={PATHS.recover}>¿Olvidó su contraseña?</Link>
          : <button type="button" className="forgot link" onClick={() => { setStep("password"); setCode(""); setError(null); void api.logout().catch(() => undefined); }}>Volver a ingresar con otra cuenta</button>}
      </form>
    </Card>
  );
}

export function Recover() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (token) {
        if (pw !== pw2) throw new Error("Las contraseñas no coinciden.");
        await api.resetPassword(token, pw);
        setMsg("Contraseña actualizada. Ya puede ingresar.");
        setTimeout(() => navigate(PATHS.login), 1500);
      } else {
        const r = await api.recover(email);
        setMsg(r.email_enabled ? "Si el correo corresponde a una cuenta, recibirá un enlace para crear una contraseña nueva."
          : "Esta instalación no tiene correo saliente: pida al administrador de su organización un enlace de recuperación.");
      }
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  };
  return (
    <Card title={token ? "Nueva contraseña" : "Recuperar contraseña"}>
      <form onSubmit={submit} className="auth-form">
        {token ? (<>
          <label className="field stacked"><span>Contraseña nueva</span>
            <PasswordInput autoComplete="new-password" required value={pw} onChange={(e) => setPw(e.target.value)} /></label>
          <label className="field stacked"><span>Repítala</span>
            <PasswordInput autoComplete="new-password" required value={pw2} onChange={(e) => setPw2(e.target.value)} /></label>
          <p className="muted small">Al menos 10 caracteres, con letras y números.</p>
        </>) : (
          <label className="field stacked"><span>Correo</span>
            <input type="email" autoComplete="username" required placeholder="correo@ejemplo.cl" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        )}
        {msg && <p className="ok-text" role="status">{msg}</p>}
        {error && <p className="field-error" role="alert">{error}</p>}
        <button className={`primary auth-submit ${busy ? "loading" : ""}`} disabled={busy || !!(msg && token)}>
          {busy && <span className="spin" aria-hidden="true" />}{token ? "Guardar contraseña" : "Enviar enlace"}</button>
        <Link className="forgot" to={PATHS.login}>Volver al ingreso</Link>
      </form>
    </Card>
  );
}

export function Invitation() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const refresh = useAuth((s) => s.refresh);
  const [info, setInfo] = useState<InvitationInfo | null>(null);
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.invitation(token).then(setInfo).catch((e) => setError(errorText(e))); }, [token]);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.acceptInvitation(token, name, pw);
      const me = await refresh();
      navigate(me?.mfa_setup_required ? `${PATHS.ajustes("seguridad")}?mfa=1` : PATHS.home, { replace: true });
    } catch (err) { setError(errorText(err)); }
  };
  return (
    <Card title="Invitación">
      {info ? (
        <form onSubmit={submit} className="auth-form">
          <p>Lo invitaron a <b>{info.org_name}</b> como <b>{ROLE_LABEL[info.role]}</b> ({info.email}).</p>
          {!info.existing_user && <label className="field stacked"><span>Su nombre</span><input required value={name} onChange={(e) => setName(e.target.value)} /></label>}
          <label className="field stacked"><span>{info.existing_user ? "Su contraseña actual" : "Contraseña"}</span>
            <PasswordInput autoComplete={info.existing_user ? "current-password" : "new-password"} required value={pw} onChange={(e) => setPw(e.target.value)} /></label>
          {!info.existing_user && <p className="muted small">Al menos 10 caracteres, con letras y números.</p>}
          {error && <p className="field-error" role="alert">{error}</p>}
          <button className="primary auth-submit">Aceptar invitación</button>
          <Link className="forgot" to={PATHS.login}>Ir al ingreso</Link>
        </form>
      ) : (<>
        <p className={error ? "field-error" : "muted"} role={error ? "alert" : undefined}>{error ?? "Cargando…"}</p>
        {error && <Link className="forgot" to={PATHS.login}>Ir al ingreso</Link>}
      </>)}
    </Card>
  );
}
