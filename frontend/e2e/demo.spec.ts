import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const evidence = "模拟测试数据：学生能清楚说明解题依据，并愿意倾听同伴的不同想法。";
const database = resolve(dirname(fileURLToPath(import.meta.url)), "../../.e2e/future9-e2e.db");

test("isolated demo job refreshes evidence, skill, events, and school coverage", async ({ page }) => {
  const roles = page.getByRole("navigation", { name: "角色切换" });
  await page.goto("/");
  await expect(page.locator(".metric")).toHaveText(/180\/720/);
  await roles.getByRole("button", { name: "学生", exact: true }).click();
  await expect(page.getByRole("option")).toHaveCount(20);
  const targetSkill = page.locator(".skills article").filter({ hasText: "BC.2" });
  await expect(targetSkill).toContainText("待收集证据");
  await roles.getByRole("button", { name: "教师", exact: true }).click();
  await page.getByPlaceholder("输入模拟测试证据").fill(evidence);
  await page.getByRole("button", { name: "保存证据" }).click();
  await page.getByRole("combobox", { name: "技能" }).selectOption("BC.2");
  await page.getByRole("button", { name: "创建 Job" }).click();
  const queued = page.getByText(/任务 #\d+：queued|任务 #\d+：running/);
  await expect(queued).toBeVisible();
  execFileSync("rtk", ["uv", "run", "python", "-c", "from backend.app.worker import process_one_job; process_one_job()"], { cwd: "..", env: { ...process.env, FUTURE9_DATABASE_PATH: database }, stdio: "inherit" });
  await expect(page.getByText(/任务 #\d+：succeeded/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/running: claimed/)).toBeVisible();
  await expect(page.getByText(/succeeded: demo_deterministic/)).toBeVisible();
  await roles.getByRole("button", { name: "学生", exact: true }).click();
  await expect(page.getByText(evidence)).toBeVisible();
  await expect(targetSkill).toContainText("等级 3");
  await roles.getByRole("button", { name: "管理员", exact: true }).click();
  await expect(page.locator(".metric")).toHaveText(/181\/720/);
});
