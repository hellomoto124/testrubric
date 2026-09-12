import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import App, { radarValues } from "./App";

const summary = { name: "共建集体", lower_median_level: 3, assessed_count: 5, skill_count: 20 };

describe("Future9 demo UI", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
  test("maps lower median levels and exposes coverage for radar tooltips", () => {
    expect(radarValues([summary, { ...summary, lower_median_level: null }])).toEqual([3, null]);
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
});
