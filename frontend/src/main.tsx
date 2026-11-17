// Tipografía del estilo v2: Inter (texto, títulos y datos) e IBM Plex Mono (código e ID), empaquetadas localmente
// con Fontsource: no dependen de la red ni de servicios externos en tiempo de ejecución (CSP: font-src 'self').
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { router } from "./routes";
import "./styles/app.css";
import "./styles/identity.css";
import "./styles/scenes.css";
import "./styles/frame.css";

// Tooltip con la opción completa en cada selector (si el ancho la recorta, se lee al pasar el mouse).
document.addEventListener("pointerover", (e) => {
  const el = e.target;
  if (el instanceof HTMLSelectElement && !el.dataset.fixedTitle) el.title = el.selectedOptions[0]?.text ?? "";
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
