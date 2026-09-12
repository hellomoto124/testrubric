import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import App, { radarOption, radarValues } from "./App";

const summary = { name: "共建集体", lower_median_level: 3, assessed_count: 5, skill_count: 20 };

describe("Future9 demo UI", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
  test("maps lower median levels and exposes coverage for radar tooltips", () => {
    expect(radarValues([summary, { ...summary, lower_median_level: null }])).toEqual([3, null]);
    expect((radarOption([summary, { ...summary, name: "自我认识", lower_median_level: null }]).series as any[])[0]).toMatchObject({ data: [{ value: [3, null] }] });
    expect(String((radarOption([summary]).tooltip as { formatter: (item: unknown) => string }).formatter({ dataIndex: 0 }))).toContain("共建集体");
  });

  test("shows simulation and non-authentication boundary", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ classes: [], students: [] }) }));
    render(<App />);
    expect(screen.getByText(/模拟测试数据/)).toBeInTheDocument();
    expect(screen.getByText(/角色切换不是认证/)).toBeInTheDocument();
  });

  test("switches visible role view", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ classes: [], students: [] }) }));
    render(<App />);
    fireEvent.click(within(screen.getByRole("navigation", { name: "角色切换" })).getByRole("button", { name: "教师" }));
    expect(await screen.findByRole("heading", { name: "教师工作台" })).toBeInTheDocument();
  });

  test("offers every simulated student from administrator view", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({ ok: true, json: async () => url === "/api/demo/context" ? { classes: [{ id: 1, name: "模拟班级" }], students: [{ id: 1, class_id: 1, anonymous_id: "模拟学生01" }, { id: 2, class_id: 1, anonymous_id: "模拟学生02" }] } : url === "/api/dashboard/school" ? { competencies: [], class_heatmap: [], level_distribution: [], coverage: {} } : { competencies: [] } })));
    render(<App />);
    expect(await screen.findByRole("button", { name: "模拟学生02" })).toBeInTheDocument();
  });
});
