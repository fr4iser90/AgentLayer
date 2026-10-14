import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Default = docker compose host port (compose maps AGENT_HTTP_PORT→container :8080).
// Uvicorn on the host: AGENT_API_TARGET=http://127.0.0.1:8080 npm run dev
const API = process.env.AGENT_API_TARGET || "http://127.0.0.1:8088";
const apiProxy = {
  "/auth": { target: API, changeOrigin: true },
  "/v1": { target: API, changeOrigin: true },
  "/health": { target: API, changeOrigin: true },
  "/openapi.json": { target: API, changeOrigin: true },
};

// Production build → apps/frontend/dist (served by FastAPI at /app)
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: apiProxy,
  },
  preview: {
    port: 4173,
    proxy: apiProxy,
  },
});
