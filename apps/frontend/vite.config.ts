import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend port differs by how it is run: 8080 when uvicorn runs directly,
// 8088 when it is reached through the docker port mapping. Overridable so
// `vite preview` can be pointed at a running stack for pixel verification
// without changing the default anyone else depends on.
const API = process.env.AGENT_API_TARGET || "http://127.0.0.1:8080";
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
