import { defineConfig } from "@playwright/test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const database = resolve(dirname(fileURLToPath(import.meta.url)), "../.e2e/future9-e2e.db");

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  globalSetup: "./e2e/global-setup.ts",
  use: { baseURL: "http://127.0.0.1:5173" },
  webServer: [
    { command: "rtk uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000", cwd: "..", env: { ...process.env, FUTURE9_DATABASE_PATH: database }, url: "http://127.0.0.1:8000/api/demo/context", reuseExistingServer: false },
    { command: "rtk pnpm dev --host 127.0.0.1 --port 5173", env: { ...process.env, FUTURE9_DATABASE_PATH: database }, url: "http://127.0.0.1:5173", reuseExistingServer: false },
  ],
});
