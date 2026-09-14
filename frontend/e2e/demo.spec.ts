import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const database = resolve(dirname(fileURLToPath(import.meta.url)), "../../.e2e/future9-e2e.db");
const evidence = "模拟测试数据：学生在合作任务中说明了自己的选择、理由和调整过程。";
const fileEvidence = "模拟测试数据：TXT 学生作品证据。";

test("V2 evidence to SSE scoring refreshes personal and school views", async ({ page }) => {
  await page.goto("/");
  const roles = page.getByRole("navigation", { name: "角色切换" });
  await expect(page.getByRole("heading", { name: "凯风雨旸素养发展总览" })).toBeVisible();
  await expect(page.getByText("基于学校三大育人目标 · 10 项核心能力 · 38 项素养技能")).toBeVisible();

  await roles.getByRole("button", { name: "学生", exact: true }).click();
  await expect(page.getByLabel("模拟学生").getByRole("option")).toHaveCount(20);
  const targetSkill = page.locator(".skill-grid button").filter({ hasText: "YY.S38" });
  await expect(targetSkill).toContainText("证据不足");

  await roles.getByRole("button", { name: "教师", exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: "work.txt", mimeType: "text/plain", buffer: Buffer.from(fileEvidence) });
  await page.getByRole("button", { name: "保存证据" }).click();
  await expect(page.getByText("已保存证据：1")).toBeVisible();
  await page.getByPlaceholder("输入模拟测试证据").fill(evidence);
  await page.getByRole("button", { name: "保存证据" }).click();
  await expect(page.getByText("已保存证据：2")).toBeVisible();
  await page.getByRole("combobox", { name: "技能" }).selectOption("YY.S38");
  await expect(page.getByLabel("任务情境")).toHaveValue("课堂合作任务");
  await expect(page.getByLabel("帮助程度")).toHaveValue("教师仅澄清任务");
  await page.getByRole("button", { name: "创建评估任务" }).click();
  await expect(page.getByText(/任务 #\d+ · (queued|running)/)).toBeVisible();

  execFileSync("rtk", ["uv", "run", "python", "-c", "from backend.app.worker import process_one_job; process_one_job()"], { cwd: "..", env: { ...process.env, FUTURE9_DATABASE_PATH: database }, stdio: "inherit" });
  await expect(page.getByText(/任务 #\d+ · succeeded/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("host_scoring")).toBeVisible();
  await expect(page.getByText("anchor_interp_v1")).toBeVisible();
  await expect(page.getByText(/指标级人工修订/)).toBeVisible();

  await roles.getByRole("button", { name: "学生", exact: true }).click();
  await expect(page.getByText(evidence)).toBeVisible();
  await expect(page.getByText(fileEvidence)).toBeVisible();
  await expect(targetSkill).toContainText(/350 分/);

  await roles.getByRole("button", { name: "管理员", exact: true }).click();
  await page.getByLabel("选择学校技能").selectOption("YY.S38");
  await expect(page.getByRole("table", { name: /连续分布文字替代/ })).toContainText("350");
});

test("375, 768 and 1440 widths do not horizontally overflow", async ({ page }) => {
  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "凯风雨旸素养发展总览" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.getByRole("navigation", { name: "角色切换" }).getByRole("button", { name: "教师", exact: true }).click();
    await expect(page.getByRole("heading", { name: "教师工作台" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.getByRole("navigation", { name: "角色切换" }).getByRole("button", { name: "学生", exact: true }).click();
    await expect(page.getByLabel("选择个人技能")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  }
});

test("administrator can open rubric, report and safe system settings", async ({ page }) => {
  await page.goto("/");
  const navigation = page.getByRole("navigation", { name: "主导航" });

  await navigation.getByRole("button", { name: /素养体系/ }).click();
  await expect(page.getByRole("heading", { name: "素养体系" })).toBeVisible();
  await expect(page.getByText("评分配置版本")).toBeVisible();
  await expect(page.getByText(/默认组间等权、组内等权/)).toBeVisible();

  await navigation.getByRole("button", { name: /报告中心/ }).click();
  await expect(page.getByRole("heading", { name: "报告中心" })).toBeVisible();
  await expect(page.getByRole("button", { name: "学校报告" })).toBeVisible();
  await page.getByRole("button", { name: "评估审计" }).click();
  await expect(page.getByRole("heading", { name: "最近评估审计" })).toBeVisible();

  await navigation.getByRole("button", { name: /系统设置/ }).click();
  await expect(page.getByRole("heading", { name: "系统设置" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "千问模型" })).toBeVisible();
  await page.getByLabel("学年", { exact: true }).fill("2027-2028");
  await page.getByRole("button", { name: "保存设置" }).click();
  await expect(page.getByText("演示系统设置已保存。")).toBeVisible();
  await expect(page.getByText(/密钥只显示“已配置”/)).toBeVisible();
});
