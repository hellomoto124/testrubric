import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: { baseURL: "http://127.0.0.1:5173" },
  webServer: [
    { command: "uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000", cwd: "..", url: "http://127.0.0.1:8000/api/demo/context", reuseExistingServer: true },
    { command: "pnpm dev --host 127.0.0.1 --port 5173", url: "http://127.0.0.1:5173", reuseExistingServer: true },
  ],
});
