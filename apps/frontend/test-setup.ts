// Shared test setup. Extends vitest's `expect` with @testing-library/jest-dom
// matchers (toBeInTheDocument / toBeDisabled / …) for component tests, and
// registers cleanup after each test. `globals` is disabled in vitest.config.ts,
// so testing-library's auto-cleanup is not registered by default — without this
// line each `render()` accumulates in document.body across tests.
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(cleanup);
