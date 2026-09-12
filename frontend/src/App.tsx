import { useCallback, useEffect, useRef, useState } from "react";
import * as echarts from "echarts";

type Role = "管理员" | "教师" | "学生";
type Summary = { name: string; level?: number | null; lower_median_level?: number | null; assessed_count?: number; skill_count?: number };
type Context = { classes: { id: number; name: string }[]; students: { id: number; class_id: number; anonymous_id: string }[] };
type Job = { id: number; status: string; events: { stage: string; detail: string }[]; results: Record<string, any>[] };
type Load<T> = { value?: T; error?: string; loading: boolean };

const get = <T,>(path: string) => fetch(path).then(async (response) => {
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
});
const coverage = (item: Summary) => `${item.assessed_count ?? 0}/${item.skill_count ?? 0}`;
export const radarValues = (items: Summary[]) => items.map((item) => item.lower_median_level ?? item.level ?? null);
export const radarOption = (summaries: Summary[]): echarts.EChartsOption => ({
  tooltip: { formatter: () => summaries.map((item, index) => `${item.name}：${radarValues(summaries)[index] ?? "未评估"}（覆盖 ${coverage(item)}）`).join("<br/>") },
  radar: { indicator: summaries.map((item) => ({ name: item.name, max: 6 })) },
  series: [{ type: "radar", data: [{ value: radarValues(summaries), name: "下中位等级" }] }],
});

function Chart({ option, onClick }: { option: echarts.EChartsOption; onClick?: (value: any) => void }) {
  const node = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!node.current || !node.current.clientWidth) return;
    const chart = echarts.init(node.current); chart.setOption(option);
    const resize = () => chart.resize(); window.addEventListener("resize", resize);
    if (onClick) chart.on("click", (event) => onClick(event.data));
    return () => { window.removeEventListener("resize", resize); chart.dispose(); };
  }, [option, onClick]);
  return <div className="chart" ref={node} aria-label="数据图表" />;
}

function Radar({ summaries }: { summaries: Summary[] }) { return <Chart option={radarOption(summaries)} />; }
function Status({ state, label }: { state: Load<unknown>; label: string }) {
  if (state.loading) return <p>{label}正在加载…</p>;
  if (state.error) return <p role="alert">{label}加载失败：{state.error}</p>;
  return null;
}

function Admin({ school, context, selectClass, selectStudent }: { school: Load<any>; context: Load<Context>; selectClass: (id: number) => void; selectStudent: (id: number) => void }) {
  if (school.loading || school.error || !school.value) return <Status state={school} label="学校看板" />;
  const value = school.value; const heatmap = value.class_heatmap ?? []; const trend = value.trend ?? [];
  const heatData = heatmap.flatMap((row: any, y: number) => row.competencies.map((item: Summary, x: number) => ({ value: [x, y, item.level ?? null], classId: row.class.id })));
  return <section><h1>学校总览</h1><div className="dashboard-grid">
    <article><h2>九项素养</h2><Radar summaries={value.competencies ?? []} /></article>
    <article><h2>班级 × 素养热力图</h2><Chart onClick={(data) => data?.classId && selectClass(data.classId)} option={{ grid: { left: 100, right: 20, bottom: 80 }, tooltip: {}, xAxis: { type: "category", data: (value.competencies ?? []).map((x: Summary) => x.name), axisLabel: { rotate: 30, interval: 0 } }, yAxis: { type: "category", data: heatmap.map((x: any) => x.class.name) }, visualMap: { min: 0, max: 6, calculable: true, orient: "horizontal", left: "center", bottom: 10 }, series: [{ type: "heatmap", data: heatData }] }} /></article>
    <article><h2>等级分布</h2><Chart option={{ xAxis: { type: "category", data: (value.level_distribution ?? []).map((x: any) => `L${x.level}`) }, yAxis: { type: "value" }, series: [{ type: "bar", data: (value.level_distribution ?? []).map((x: any) => x.count) }] }} /></article>
    <article><h2>覆盖率</h2><p className="metric">{value.coverage?.assessed_count ?? 0}/{value.coverage?.skill_count ?? 0}（{Math.round((value.coverage?.coverage ?? 0) * 100)}%）</p><h2>评估趋势</h2><Chart option={{ xAxis: { type: "category", data: trend.map((x: any) => x.date) }, yAxis: { type: "value" }, series: [{ type: "line", data: trend.map((x: any) => x.assessed_count), symbolSize: 8, label: { show: trend.length === 1 } }] }} /></article>
  </div><h2>20 名模拟学生入口</h2><Status state={context} label="学生名单" /><div className="matrix">{context.value?.students.map((student) => <button key={student.id} onClick={() => selectStudent(student.id)}>{student.anonymous_id}</button>)}</div><p>点击热力图进入教师视图；不显示任何学生排名。</p></section>;
}

function useJobMonitor(job: Job | undefined, setJob: (value: Job) => void, onTerminal: () => void, setError: (message: string) => void) {
  const sourceRef = useRef<EventSource | null>(null); const timerRef = useRef<number | null>(null);
  useEffect(() => {
    if (!job || ["succeeded", "failed"].includes(job.status)) return;
    const stop = () => { sourceRef.current?.close(); sourceRef.current = null; if (timerRef.current !== null) window.clearInterval(timerRef.current); timerRef.current = null; };
    const read = async () => {
      try { const current = await get<Job>(`/api/assessment-jobs/${job.id}`); setJob(current); if (["succeeded", "failed"].includes(current.status)) { stop(); onTerminal(); } }
      catch (error) { stop(); setError(`任务状态查询失败：${String(error)}`); }
    };
    sourceRef.current = new EventSource(`/api/assessment-jobs/${job.id}/events`);
    sourceRef.current.addEventListener("status", read); sourceRef.current.onerror = () => { stop(); setError("任务进度连接失败"); };
    timerRef.current = window.setInterval(read, 500);
    return stop;
  }, [job?.id, job?.status, setJob, onTerminal, setError]);
}

function Teacher({ context, classId, setClassId, openStudent, skills, onJobTerminal }: { context: Load<Context>; classId: number; setClassId: (value: number) => void; openStudent: (id: number) => void; skills: any[]; onJobTerminal: () => void }) {
  const [dashboard, setDashboard] = useState<Load<any>>({ loading: true }); const [studentId, setStudentId] = useState(0); const [evidenceType, setEvidenceType] = useState("teacher_observation"); const [text, setText] = useState(""); const [file, setFile] = useState<File>(); const [evidenceRefs, setEvidenceRefs] = useState<number[]>([]); const [skillCode, setSkillCode] = useState(""); const [job, setJob] = useState<Job>(); const [error, setError] = useState(""); const [nextStep, setNextStep] = useState("");
  useEffect(() => { if (!classId) return; setDashboard({ loading: true }); get<any>(`/api/classes/${classId}/dashboard`).then((value) => { setDashboard({ loading: false, value }); setStudentId(value.students?.[0]?.id ?? 0); }).catch((e) => setDashboard({ loading: false, error: String(e) })); }, [classId]);
  useJobMonitor(job, setJob, onJobTerminal, setError);
  const classStudents = context.value?.students.filter((item) => item.class_id === classId) ?? [];
  const submitEvidence = async (event: React.FormEvent) => { event.preventDefault(); setError(""); const body = new FormData(); body.set("student_id", String(studentId)); body.set("evidence_type", evidenceType); body.set("text", text); if (file) body.set("file", file); try { const evidence = await fetch("/api/evidence", { method: "POST", body }).then(async (response) => { if (!response.ok) throw new Error(await response.text()); return response.json(); }); setEvidenceRefs((value) => [...value, evidence.id]); setText(""); setFile(undefined); } catch (e) { setError(String(e)); } };
  const createJob = async () => { try { const created = await fetch("/api/assessment-jobs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ student_id: studentId, skill_code: skillCode, evidence_refs: evidenceRefs }) }).then(async (response) => { if (!response.ok) throw new Error(await response.text()); return response.json(); }); setJob(created); } catch (e) { setError(String(e)); } };
  const revise = async () => { const current = job?.results.at(-1); if (!current || !nextStep) return; try { const updated = await fetch(`/api/assessments/${current.id}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ ...current, next_step: nextStep }) }).then(async (response) => { if (!response.ok) throw new Error(await response.text()); return response.json(); }); setJob(updated); } catch (e) { setError(String(e)); } };
  return <section><h1>教师工作台</h1><Status state={context} label="班级名单" /><label>班级 <select value={classId} onChange={(e) => setClassId(Number(e.target.value))}>{context.value?.classes.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><Status state={dashboard} label="班级看板" />
    <div className="matrix">{(dashboard.value?.students ?? classStudents).map((student: any) => <button key={student.id} onClick={() => openStudent(student.id)}><b>{student.anonymous_id}</b><span>{(student.competencies ?? []).slice(0, 3).map((item: Summary) => `${item.name} ${item.level ?? "–"}`).join(" · ")}</span><small>查看个人页了解全部九项素养</small></button>)}</div>
    <form onSubmit={submitEvidence}><h2>证据录入</h2><label>学生 <select value={studentId} onChange={(e) => setStudentId(Number(e.target.value))}>{classStudents.map((item) => <option key={item.id} value={item.id}>{item.anonymous_id}</option>)}</select></label><label>证据类型 <select value={evidenceType} onChange={(e) => setEvidenceType(e.target.value)}><option value="teacher_observation">教师观察</option><option value="student_self_reflection">学生自评</option><option value="student_work">学生作品</option></select></label><textarea required={!file} value={text} onChange={(e) => setText(e.target.value)} placeholder="输入模拟测试证据" /><input key={evidenceRefs.length} type="file" onChange={(e) => setFile(e.target.files?.[0])} /><button>保存证据</button>{evidenceRefs.length > 0 && <p>已保存证据：{evidenceRefs.length}</p>}</form>
    <h2>创建评估任务</h2><label>技能 <select value={skillCode} onChange={(e) => setSkillCode(e.target.value)}><option value="">请选择</option>{skills.map((skill) => <option key={skill.code} value={skill.code}>{skill.code} · {skill.name}</option>)}</select></label><button disabled={!studentId || !skillCode || !evidenceRefs.length} onClick={createJob}>创建 Job</button>
    {job && <article><h2>任务 #{job.id}：{job.status}</h2><p>{job.events.map((event) => `${event.stage}: ${event.detail}`).join(" · ")}</p>{job.results.map((result, index) => <p key={String(result.id)}>修订 {String(result.revision ?? index + 1)}：等级 {String(result.level ?? "未评估")}；{String(result.rationale ?? "")}</p>)}<input aria-label="人工修订建议" value={nextStep} onChange={(e) => setNextStep(e.target.value)} placeholder="人工修订下一步建议" /><button onClick={revise} disabled={!nextStep}>按 result id 人工修订</button></article>}{error && <p role="alert">{error}</p>}
  </section>;
}

function Student({ context, studentId, setStudentId, refreshKey }: { context: Load<Context>; studentId: number; setStudentId: (value: number) => void; refreshKey: number }) {
  const [profile, setProfile] = useState<Load<any>>({ loading: true });
  useEffect(() => { if (!studentId) return; setProfile({ loading: true }); get<any>(`/api/students/${studentId}/profile`).then((value) => setProfile({ loading: false, value })).catch((e) => setProfile({ loading: false, error: String(e) })); }, [studentId, refreshKey]);
  const value = profile.value;
  return <section><h1>我的成长档案</h1><Status state={context} label="学生名单" /><label>模拟学生 <select value={studentId} onChange={(e) => setStudentId(Number(e.target.value))}>{context.value?.students.map((item) => <option key={item.id} value={item.id}>{item.anonymous_id}</option>)}</select></label><Status state={profile} label="学生档案" />{value && <><div className="student-overview"><Radar summaries={value.competencies ?? []} /><article><h2>亮点摘要</h2><p>{value.skills.filter((item: any) => item.result?.status === "assessed").slice(0, 3).map((item: any) => item.name).join("、") || "继续收集具体学习例子。"}</p><h2>下一步建议</h2><p>{value.skills.map((item: any) => item.result?.next_step).find(Boolean) ?? "收集一个具体学习例子。"}</p><small>模拟测试数据 / AI 自动评估 / 非正式成绩</small></article></div><h2>36 项技能</h2><div className="skills">{value.skills.map((skill: any) => <article key={skill.code}><b className="skill-title" title={`${skill.code} · ${skill.name}`}>{skill.code} · {skill.name}</b><span>{skill.result?.status === "assessed" ? `等级 ${skill.result.level}` : "待收集证据"}</span></article>)}</div><h2>证据时间线</h2><div className="timeline"><ol>{value.evidence_timeline.map((item: any) => <li key={item.id}>{item.created_at} · {item.evidence_type} · {item.text || item.filename}</li>)}</ol></div></>}</section>;
}

export default function App() {
  const [role, setRole] = useState<Role>("管理员"); const [context, setContext] = useState<Load<Context>>({ loading: true }); const [school, setSchool] = useState<Load<any>>({ loading: true }); const [rubric, setRubric] = useState<Load<any>>({ loading: true }); const [classId, setClassId] = useState(0); const [studentId, setStudentId] = useState(0); const [refreshKey, setRefreshKey] = useState(0);
  const refreshSchool = useCallback(() => { setSchool({ loading: true }); get<any>("/api/dashboard/school").then((value) => setSchool({ loading: false, value })).catch((e) => setSchool({ loading: false, error: String(e) })); }, []);
  useEffect(() => { get<Context>("/api/demo/context").then((value) => { setContext({ loading: false, value }); setClassId(value.classes[0]?.id ?? 0); setStudentId(value.students[0]?.id ?? 0); }).catch((e) => setContext({ loading: false, error: String(e) })); get<any>("/api/rubrics/current").then((value) => setRubric({ loading: false, value })).catch((e) => setRubric({ loading: false, error: String(e) })); refreshSchool(); }, [refreshSchool]);
  useEffect(() => { if (role === "管理员") refreshSchool(); }, [role, refreshSchool]);
  const skills = rubric.value?.competencies?.flatMap((item: any) => item.skills) ?? []; const onJobTerminal = useCallback(() => { setRefreshKey((value) => value + 1); refreshSchool(); }, [refreshSchool]); const openClass = (id: number) => { setClassId(id); setRole("教师"); }; const openStudent = (id: number) => { setStudentId(id); setRole("学生"); };
  return <><header className="notice"><strong>模拟测试数据 / AI 自动评估 / 非正式成绩</strong><span>角色切换不是认证，不代表真实身份或权限。</span></header><nav aria-label="角色切换">{(["管理员", "教师", "学生"] as Role[]).map((item) => <button key={item} className={role === item ? "active" : ""} onClick={() => setRole(item)}>{item}</button>)}</nav><main><Status state={rubric} label="量规" />{role === "管理员" && <Admin school={school} context={context} selectClass={openClass} selectStudent={openStudent} />}{role === "教师" && <Teacher context={context} classId={classId} setClassId={setClassId} openStudent={openStudent} skills={skills} onJobTerminal={onJobTerminal} />}{role === "学生" && <Student context={context} studentId={studentId} setStudentId={setStudentId} refreshKey={refreshKey} />}</main></>;
}
