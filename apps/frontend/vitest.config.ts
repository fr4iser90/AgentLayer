import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Unit + component tests for the frontend. Kept separate from `vite.config.ts`
// (production build) so the test runner (jsdom, globals, setupFiles) does not
// leak into the production bundle config. Exported scripts: `test:unit` (run)
// and `test:unit:watch` (watch).
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./test-setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
