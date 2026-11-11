import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { router } from "./routes";
import "./styles/app.css";

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
