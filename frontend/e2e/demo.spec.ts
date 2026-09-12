import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

test("teacher submits simulated evidence, worker finishes, and dashboards refresh", async ({ page }) => {
  const roles = page.getByRole("navigation", { name: "角色切换" });
  await page.goto("/");
  await expect(page.getByText(/模拟测试数据/)).toBeVisible();
  await roles.getByRole("button", { name: "学生", exact: true }).click();
  await expect(page.getByRole("option")).toHaveCount(20);
  await expect(page.getByText("36 项技能")).toBeVisible();
  await roles.getByRole("button", { name: "教师", exact: true }).click();
  await expect(page.getByRole("heading", { name: "教师工作台" })).toBeVisible();
  await page.getByPlaceholder("输入模拟测试证据").fill("模拟测试数据：学生能清楚说明解题依据，并愿意倾听同伴的不同想法。");
  await page.getByRole("button", { name: "保存证据" }).click();
  await expect(page.getByText(/创建评估任务/)).toBeVisible();
  await page.getByRole("combobox", { name: "技能" }).selectOption({ index: 1 });
  await page.getByRole("button", { name: "创建 Job" }).click();
  const queued = page.getByText(/任务 #\d+：queued|任务 #\d+：running/);
  await expect(queued).toBeVisible();
  const jobId = Number((await queued.textContent())?.match(/#(\d+)/)?.[1]);
  execFileSync("uv", ["run", "python", "-c", `from backend.app.database import get_job; from backend.app.worker import process_one_job; [process_one_job() for _ in range(50) if get_job(${jobId})['status'] not in {'succeeded', 'failed'}]`], { cwd: "..", stdio: "inherit" });
  await expect(page.getByText(/任务 #\d+：succeeded/)).toBeVisible({ timeout: 10_000 });
  await roles.getByRole("button", { name: "学生", exact: true }).click();
  await expect(page.getByText("证据时间线")).toBeVisible();
  await roles.getByRole("button", { name: "管理员", exact: true }).click();
  await expect(page.getByRole("heading", { name: "学校总览" })).toBeVisible();
});
