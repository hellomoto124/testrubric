import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const database = resolve(dirname(fileURLToPath(import.meta.url)), "../../.e2e/future9-e2e.db");

export default function globalSetup() {
  mkdirSync(dirname(database), { recursive: true });
  rmSync(database, { force: true });
  rmSync(`${database}-journal`, { force: true });
  rmSync(`${database}-shm`, { force: true });
  rmSync(`${database}-wal`, { force: true });
  execFileSync("rtk", ["uv", "run", "python", "-c", "from backend.app.database import initialize; from backend.app.main import RUBRIC; initialize(RUBRIC)"], { cwd: resolve(dirname(fileURLToPath(import.meta.url)), "../.."), env: { ...process.env, FUTURE9_DATABASE_PATH: database }, stdio: "inherit" });
}
