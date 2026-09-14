import { useEffect, useMemo, useState } from "react";

const json = async (path: string, init?: RequestInit) => {
  const response = await fetch(path, init);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};
const write = (method: string, path: string, body?: unknown) => json(path, {
  method,
  headers: body ? { "content-type": "application/json" } : undefined,
  body: body ? JSON.stringify(body) : undefined,
});

const flattenSkills = (rubric: any) => (rubric?.hierarchy ?? []).flatMap((goal: any) => goal.capabilities.flatMap((capability: any) => capability.skills));

export function RubricSystem({ rubric }: { rubric: any }) {
  const skills = useMemo(() => flattenSkills(rubric), [rubric]);
  const [skillCode, setSkillCode] = useState("YY.S01");
  const [config, setConfig] = useState<any>();
  const [configs, setConfigs] = useState<any[]>([]);
  const [targets, setTargets] = useState<any[]>([]);
  const [targetLevel, setTargetLevel] = useState(3);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const selected = skills.find((item: any) => item.code === skillCode);
  const load = async () => {
    try {
      const [published, versions, targetRows] = await Promise.all([
        json(`/api/v2/skills/${skillCode}/scoring-rubric`),
        json(`/api/v2/scoring-rubrics?skill_code=${skillCode}`),
        json(`/api/v2/targets?skill_code=${skillCode}`),
      ]);
      setConfig(published); setConfigs(versions.items); setTargets(targetRows.items);
      setTargetLevel(targetRows.items.at(-1)?.target_level ?? 3); setError("");
    } catch (reason) { setError(String(reason)); }
  };
  useEffect(() => { if (skills.length) void load(); }, [skillCode, skills.length]);
  const saveTarget = async () => {
    try { await write("PUT", `/api/v2/targets/3-6/ui/${skillCode}`, { target_level: targetLevel, target_version: `ui-${Date.now()}` }); setMessage("新目标版本已保存，仅影响后续比较。"); await load(); } catch (reason) { setError(String(reason)); }
  };
  const createDraft = async () => {
    try { const draft = await write("POST", "/api/v2/scoring-rubrics/drafts", { skill_code: skillCode }); setMessage(`已创建评分配置 V${draft.version} 草稿。`); await load(); } catch (reason) { setError(String(reason)); }
  };
  const transition = async (item: any) => {
    try {
      if (item.status === "draft") await write("PATCH", `/api/v2/scoring-rubrics/${item.id}`, { status: "reviewed" });
      else if (item.status === "reviewed") await write("POST", `/api/v2/scoring-rubrics/${item.id}/publish`);
      setMessage(item.status === "draft" ? "配置已标记为已复核。" : "配置已发布，旧版本已归档。"); await load();
    } catch (reason) { setError(String(reason)); }
  };
  return <div className="page admin-module"><header className="module-heading"><div><small>教研管理员 · 教师只读</small><h1>素养体系</h1><p>管理 3 个育人目标、10 项能力、38 项技能及连续评分依据。</p></div><span>当前量规：kai_feng_yuyang_260910</span></header><div className="rubric-workspace"><aside className="rubric-tree">{(rubric?.hierarchy ?? []).map((goal: any) => <details open key={goal.code}><summary>{goal.code} · {goal.name}</summary>{goal.capabilities.map((capability: any) => <div key={capability.code}><b>{capability.code} · {capability.name}</b>{capability.skills.map((skill: any) => <button type="button" className={skill.code === skillCode ? "active" : ""} onClick={() => setSkillCode(skill.code)} key={skill.code}>{skill.code} · {skill.name_cn}</button>)}</div>)}</details>)}</aside><section className="rubric-detail"><div className="section-heading"><div><small>{skillCode}</small><h2>{selected?.name_cn}</h2></div><select aria-label="选择量规技能" value={skillCode} onChange={(event) => setSkillCode(event.target.value)}>{skills.map((skill: any) => <option key={skill.code} value={skill.code}>{skill.code} · {skill.name_cn}</option>)}</select></div><div className="rubric-toolbar"><label>三年级目标<select value={targetLevel} onChange={(event) => setTargetLevel(Number(event.target.value))}>{[1, 2, 3, 4, 5, 6].map((level) => <option key={level} value={level}>Level {level}</option>)}</select></label><button type="button" onClick={saveTarget}>保存新目标版本</button><button className="primary" type="button" onClick={createDraft}>基于已发布版本创建草稿</button></div><p className="boundary-note">学校演示目标，不是 Future9 官方年级映射。默认组间等权、组内等权，普通教师无需填写百分比。</p>{message && <p className="success-note">{message}</p>}{error && <p role="alert">{error}</p>}<h3>评分配置版本</h3><div className="version-list">{configs.map((item) => <article key={item.id}><b>V{item.version}</b><span>{item.status}</span><small>{item.group_count} 个指标组 · {item.calibration_status}</small>{["draft", "reviewed"].includes(item.status) && <button type="button" onClick={() => transition(item)}>{item.status === "draft" ? "提交复核" : "发布版本"}</button>}</article>)}</div><h3>已发布配置审查</h3><div className="review-columns"><b>原量规要求</b><b>指标与0—4档行为锚点</b><b>示例证据与预期判断</b>{(config?.groups ?? []).map((group: any) => <div className="review-row" key={group.id}><div><strong>Level {group.level}</strong>{group.indicators.map((indicator: any) => <p key={indicator.id}>{indicator.source_text}</p>)}</div><div>{group.indicators.map((indicator: any) => <details key={indicator.id}><summary>{indicator.id}</summary><ol>{indicator.anchors.map((anchor: any) => <li key={anchor.score}><b>{anchor.score}档</b> {anchor.text}</li>)}</ol></details>)}</div><div><p>模拟课堂证据应包含具体行为、情境、帮助程度和展示机会。</p><p>模型只提交指标档位；后端计算 Level、区间和目标差距。</p></div></div>)}</div><p className="target-history">目标版本：{targets.map((item) => `${item.target_version}=L${item.target_level}`).join(" · ")}</p></section></div></div>;
}

function ReportDashboard({ dashboard }: { dashboard: any }) {
  if (!dashboard) return <p>正在加载报告…</p>;
  return <><section className="report-metrics"><div><b>{dashboard.student_count}</b><span>学生</span></div><div><b>{dashboard.goals.length}</b><span>育人目标</span></div><div><b>{dashboard.goals.flatMap((goal: any) => goal.capabilities).length}</b><span>素养能力</span></div><div><b>{dashboard.goals.flatMap((goal: any) => goal.capabilities.flatMap((capability: any) => capability.skills)).length}</b><span>技能</span></div></section><div className="report-goals">{dashboard.goals.map((goal: any) => <article key={goal.code}><small>{goal.code}</small><h2>{goal.name}</h2><b>{goal.median_level ? `中位 Level ${goal.median_level}` : "尚无明确中位水平"}</b><span>覆盖 {Math.round((goal.coverage ?? 0) * 100)}%</span><ul>{goal.capabilities.map((item: any) => <li key={item.code}>{item.name} · {Math.round((item.coverage ?? 0) * 100)}%</li>)}</ul></article>)}</div></>;
}

export function ReportCenter({ context }: { context: any }) {
  const [scope, setScope] = useState("school");
  const [subjectId, setSubjectId] = useState(1);
  const [dashboard, setDashboard] = useState<any>();
  const [audit, setAudit] = useState<any[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (scope === "audit") { json("/api/v2/reports/audit?limit=30").then((value) => { setAudit(value.items); setError(""); }).catch((reason) => setError(String(reason))); return; }
    json(`/api/v2/dashboard/${scope}/${scope === "school" ? 1 : subjectId}`).then((value) => { setDashboard(value); setError(""); }).catch((reason) => setError(String(reason)));
  }, [scope, subjectId]);
  return <div className="page admin-module"><header className="module-heading"><div><small>网页报告 · 非正式成绩</small><h1>报告中心</h1><p>查看学校、班级、个人与评估审计报告。</p></div></header><nav className="report-tabs" aria-label="报告类型">{[["school", "学校报告"], ["class", "班级报告"], ["student", "个人报告"], ["audit", "评估审计"]].map(([value, label]) => <button className={scope === value ? "active" : ""} type="button" key={value} onClick={() => setScope(value)}>{label}</button>)}</nav>{scope === "class" && <label className="report-filter">选择班级<select value={subjectId} onChange={(event) => setSubjectId(Number(event.target.value))}>{context?.classes?.map((item: any) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}{scope === "student" && <label className="report-filter">选择学生<select value={subjectId} onChange={(event) => setSubjectId(Number(event.target.value))}>{context?.students?.map((item: any) => <option key={item.id} value={item.id}>{item.anonymous_id}</option>)}</select></label>}{error && <p role="alert">{error}</p>}{scope !== "audit" ? <ReportDashboard dashboard={dashboard} /> : <section className="audit-table"><h2>最近评估审计</h2><div className="table-scroll"><table><thead><tr><th>任务</th><th>学生</th><th>技能</th><th>状态</th><th>量规</th><th>评分版本</th><th>目标版本</th><th>执行引擎</th></tr></thead><tbody>{audit.map((item) => <tr key={item.job_id}><td>#{item.job_id}</td><td>{item.student_id}</td><td>{item.skill_code}</td><td>{item.status}</td><td>{item.rubric_code}</td><td>V{item.scoring_config_version}</td><td>{item.target_version}</td><td>{item.engine ?? "—"}</td></tr>)}</tbody></table></div></section>}<p className="boundary-note">首期仅提供网页报告，不导出PDF、Excel或正式成绩单。</p></div>;
}

export function SystemSettings() {
  const [status, setStatus] = useState<any>();
  const [settings, setSettings] = useState({ academic_year: "", term: "", default_grade: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const load = () => json("/api/v2/system/status").then((value) => { setStatus(value); setSettings(value.settings); setError(""); }).catch((reason) => setError(String(reason)));
  useEffect(() => { void load(); }, []);
  const save = async (event: React.FormEvent) => { event.preventDefault(); try { await write("PUT", "/api/v2/system/settings", settings); setMessage("演示系统设置已保存。"); await load(); } catch (reason) { setError(String(reason)); } };
  return <div className="page admin-module"><header className="module-heading"><div><small>演示管理员设置</small><h1>系统设置</h1><p>管理学期信息，检查模型、worker、数据库和量规状态。</p></div></header>{!status ? <p>{error || "正在读取系统状态…"}</p> : <><form className="settings-form" onSubmit={save}><h2>学校与学期</h2><label>学年<input value={settings.academic_year} onChange={(event) => setSettings({ ...settings, academic_year: event.target.value })} /></label><label>学期<input value={settings.term} onChange={(event) => setSettings({ ...settings, term: event.target.value })} /></label><label>默认年级<input value={settings.default_grade} onChange={(event) => setSettings({ ...settings, default_grade: event.target.value })} /></label><button className="primary">保存设置</button>{message && <p className="success-note">{message}</p>}</form><section className="system-grid"><article><h2>千问模型</h2><dl><dt>模型</dt><dd>{status.model.name ?? "未配置"}</dd><dt>兼容端点</dt><dd>{status.model.base_url ?? "未配置"}</dd><dt>API Key</dt><dd>{status.model.api_key_configured ? "已配置（密钥隐藏）" : "未配置"}</dd><dt>视觉</dt><dd>{status.model.vision_enabled ? "已启用" : "未启用"}</dd><dt>运行模式</dt><dd>{status.model.demo_agent_mode ? "确定性模拟" : "真实模型"}</dd></dl></article><article><h2>Worker与任务</h2><p className={`health ${status.worker.status}`}>{status.worker.status === "online" ? "在线" : "离线"}</p><dl>{Object.entries(status.worker.jobs).map(([key, value]) => <span key={key}><dt>{key}</dt><dd>{String(value)}</dd></span>)}</dl></article><article><h2>数据与量规</h2><dl><dt>数据库</dt><dd>{status.database.status}</dd><dt>学生</dt><dd>{status.data_counts.students}</dd><dt>证据</dt><dd>{status.data_counts.evidence}</dd><dt>V2结果</dt><dd>{status.data_counts.v2_results}</dd><dt>量规</dt><dd>{status.rubric.code}</dd><dt>评分引擎</dt><dd>{status.rubric.scoring_version}</dd></dl></article></section><section className="failure-list"><h2>最近失败任务</h2>{status.recent_failures.length ? status.recent_failures.map((item: any) => <p key={item.job_id}>#{item.job_id} · {item.skill_code} · {item.error}</p>) : <p>暂无失败任务。</p>}</section><p className="boundary-note">密钥只显示“已配置”，不能在页面查看或修改；不提供数据删除、重置、登录权限或多学校设置。</p></>}</div>;
}
