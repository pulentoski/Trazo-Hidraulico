import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

function App() {
  return <main style={{ fontFamily: "sans-serif", padding: 24 }}>Trazo Hidráulico — infraestructura en marcha.</main>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
