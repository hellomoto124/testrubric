import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import App, { scoreLabel } from "./App";

const skill = { code: "YY.S01", name: "识别并调适自身感受", target_level: 3, coverage: .5, score_points: [300, 342], score_intervals: [{ lower: 280, upper: 340 }], result: { id: 1, revision: 1, score_state: "bounded", attained_level: 2, score_lower: 280, score_upper: 340 } };
const goals = [
  { code: "YY.G01", name: "富有社会担当的关怀者", median_level: 3, coverage: .5, capabilities: [{ code: "YY.C01", name: "通情达理", skills: [skill] }] },
  { code: "YY.G02", name: "怀有人生理想的创造者", median_level: 2, coverage: .4, capabilities: [{ code: "YY.C02", name: "参与探究", skills: [] }] },
  { code: "YY.G03", name: "拥有良好习惯的学习者", median_level: null, coverage: 0, capabilities: [{ code: "YY.C03", name: "学会学习", skills: [] }] },
];
const context = { classes: [{ id: 1, name: "模拟测试班级1" }], students: [{ id: 1, class_id: 1, anonymous_id: "模拟学生01" }, { id: 2, class_id: 1, anonymous_id: "模拟学生02" }] };
const dashboard = { scope: { type: "school", id: 1 }, subject: { id: 1, name: "凯风雨旸小学（模拟测试数据）" }, student_count: 20, rubric_code: "kai_feng_yuyang_260910", scoring_version: "anchor_interp_v1", goals };

function mockApi() {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    const body = url === "/api/demo/context" ? context : url === "/api/v2/rubrics/current" ? { hierarchy: goals } : url.includes("/api/v2/dashboard/") ? dashboard : url.includes("/profile") ? { evidence_timeline: [] } : url.includes("/history") ? { items: [] } : {};
    return Promise.resolve({ ok: true, json: async () => body, text: async () => JSON.stringify(body) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("凯风雨旸小学 V2 UI", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  test("keeps exact, bounded, insufficient and legacy states distinct", () => {
    expect(scoreLabel({ score_state: "exact", score_display: 342 } as any)).toBe("342 分");
    expect(scoreLabel({ score_state: "bounded", score_lower: 280, score_upper: 340 } as any)).toBe("[280, 340]");
    expect(scoreLabel({ score_state: "insufficient_evidence" } as any)).toBe("证据不足");
    expect(scoreLabel({ score_state: "legacy_unscored" } as any)).toContain("未连续计分");
  });

  test("loads V2 rubric and dashboard with simulation boundary", async () => {
    const fetchMock = mockApi();
    render(<App />);
    expect(screen.getByText(/模拟测试数据/)).toBeInTheDocument();
    expect(screen.getByText(/角色切换不是认证/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "学校素养地图" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/v2/rubrics/current");
    expect(fetchMock).toHaveBeenCalledWith("/api/v2/dashboard/school/1");
  });

  test("renders three goals and chart text alternative", async () => {
    mockApi();
    render(<App />);
    expect(await screen.findByText("富有社会担当的关怀者")).toBeInTheDocument();
    expect(screen.getByText("怀有人生理想的创造者")).toBeInTheDocument();
    expect(screen.getByText("拥有良好习惯的学习者")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /连续分布文字替代/ })).toHaveTextContent("[280, 340]");
  });

  test("switches to teacher and exposes V2 evidence context fields", async () => {
    mockApi();
    render(<App />);
    fireEvent.click(within(screen.getByRole("navigation", { name: "角色切换" })).getByRole("button", { name: "教师" }));
    expect(await screen.findByRole("heading", { name: "教师工作台" })).toBeInTheDocument();
    expect(screen.getByLabelText("任务情境")).toHaveValue("课堂合作任务");
    expect(screen.getByLabelText("帮助程度")).toHaveValue("教师仅澄清任务");
  });
});
