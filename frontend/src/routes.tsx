// Rutas de la aplicación.
//
// La estructura queda preparada para la etapa 5 (usuarios): /login se agregará como ruta pública y las rutas
// de trabajo cuelgan de <RequireAuth>, que hoy deja pasar todo (el sitio se protege con basic auth en Caddy).
// Ver docs/autenticacion.md.
import { Outlet, createBrowserRouter } from "react-router";
import { About } from "./pages/About";
import { EditorPage } from "./pages/Editor";
import { Home } from "./pages/Home";
import { NotFound } from "./pages/NotFound";
import { PATHS } from "./paths";
import { Settings } from "./pages/Settings";
import { Shell } from "./pages/Shell";

/** Guardián de rutas protegidas. Etapa 5: redirigir a /login si no hay sesión válida. */
export function RequireAuth() {
  return <Outlet />;
}

export const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      // Rutas públicas (etapa 5: { path: "/login", element: <Login /> }).
      {
        element: <RequireAuth />,
        children: [
          { path: PATHS.home, element: <Home /> },
          { path: PATHS.settings, element: <Settings /> },
          { path: PATHS.about, element: <About /> },
          { path: "/proyecto/:id", element: <EditorPage /> },
        ],
      },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
