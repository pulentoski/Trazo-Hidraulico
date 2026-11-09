import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8080" } },
  build: { target: "es2022", sourcemap: false, chunkSizeWarningLimit: 900 },
  // El contenedor de pruebas tiene el sistema de archivos de solo lectura: caché en /tmp.
  cacheDir: "/tmp/vite-cache",
  test: { environment: "node", include: ["src/**/*.test.ts"], fsModuleCache: false },
});
