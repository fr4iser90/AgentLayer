import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

/**
 * Standalone build for the tooltip probe. Kept out of the app's own build so the
 * probe can never ship or affect `npm run build`. Tailwind still resolves: the
 * PostCSS config and tailwind.config.js sit one level up in apps/frontend, and
 * their content globs cover src/**, which is where Tooltip.tsx lives.
 */
export default defineConfig({
  root: here,
  plugins: [react()],
  build: {
    outDir: join(here, ".probe-dist"),
    emptyOutDir: true,
    minify: false,
  },
});
