import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import pkg from "./package.json" with { type: "json" };

export default defineConfig({
  plugins: [react()],
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8080" } },
  // El worker de MapLibre se crea como módulo (new Worker(url, { type: "module" })).
  worker: { format: "es" },
  build: { target: "es2022", sourcemap: false, chunkSizeWarningLimit: 900 },
  // El contenedor de pruebas tiene el sistema de archivos de solo lectura: caché en /tmp.
  cacheDir: "/tmp/vite-cache",
  test: { environment: "node", include: ["src/**/*.test.ts"], fsModuleCache: false },
});
