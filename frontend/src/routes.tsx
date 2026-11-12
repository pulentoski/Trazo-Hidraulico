// Rutas de la aplicación: públicas (ingreso, recuperación, invitación) y de trabajo, protegidas por <RequireAuth>.
import { useEffect } from "react";
import { Navigate, Outlet, createBrowserRouter, useLocation } from "react-router";

/** Rutas antiguas (Perfil, Organización, Plataforma, Configuración, Acerca de) → su sección de Ajustes. */
function Legacy({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate to={`${to}${search}`} replace />;
}
import { api } from "./api/client";
import { Ajustes } from "./pages/Ajustes";
import { Invitation, Login, Recover } from "./pages/Auth";
import { EditorPage } from "./pages/Editor";
import { GestionPage } from "./pages/Gestion";
import { Home } from "./pages/Home";
import { NotFound } from "./pages/NotFound";
import { PATHS } from "./paths";
import { Shell } from "./pages/Shell";
import { useAuth } from "./state/auth";
import { useEditor } from "./state/store";
import { Skeleton } from "./components/Skeleton";

/** Guardián de rutas: sin sesión → /login?volver=…; con TOTP obligatorio sin configurar → /ajustes/seguridad. */
export function RequireAuth() {
  const { status, me, refresh } = useAuth();
  const location = useLocation();
  const set = useEditor((s) => s.set);
  useEffect(() => { if (status === "loading") void refresh(); }, [status, refresh]);
  useEffect(() => {
    if (status !== "ok" || !me || me.mfa_setup_required || me.mfa_pending) return;
    // Datos de referencia: una vez por carga de la aplicación (no en cada refresco de la sesión).
    const st = useEditor.getState();
    if (st.catalog.length && st.profiles.length && st.engine) return;
    Promise.all([api.catalog(), api.profiles(), api.engine()])
      .then(([catalog, profiles, engine]) => set({ catalog, profiles, engine }))
      .catch(() => undefined);
  }, [status, me, set]);
  if (status === "loading") return <Skeleton kind="page" />;
  const back = encodeURIComponent(location.pathname + location.search);
  if (status === "anon" || !me || me.mfa_pending) return <Navigate to={`${PATHS.login}?volver=${back}`} replace />;
  if (me.mfa_setup_required && location.pathname !== PATHS.ajustes("seguridad")) return <Navigate to={`${PATHS.ajustes("seguridad")}?mfa=1`} replace />;
  return <Outlet />;
}

export const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { path: PATHS.login, element: <Login /> },
      { path: PATHS.recover, element: <Recover /> },
      { path: PATHS.invitation, element: <Invitation /> },
      {
        element: <RequireAuth />,
        children: [
          { path: PATHS.home, element: <Home /> },
          { path: "/ajustes", element: <Navigate to={PATHS.ajustes("perfil")} replace /> },
          { path: "/ajustes/:seccion", element: <Ajustes /> },
          { path: "/perfil", element: <Legacy to={PATHS.ajustes("seguridad")} /> },
          { path: "/organizacion", element: <Legacy to={PATHS.ajustes("miembros")} /> },
          { path: "/plataforma", element: <Legacy to={PATHS.ajustes("organizaciones")} /> },
          { path: "/configuracion", element: <Legacy to={PATHS.ajustes("preferencias")} /> },
          { path: "/acerca-de", element: <Legacy to={PATHS.ajustes("perfil")} /> },
          { path: "/proyecto/:id", element: <EditorPage /> },
          { path: "/proyecto/:id/gestion", element: <GestionPage /> },
        ],
      },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
