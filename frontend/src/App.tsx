import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";

type Role = "管理员" | "教师" | "学生";
type Summary = { name: string; level?: number | null; lower_median_level?: number | null; assessed_count?: number; skill_count?: number; coverage?: number };
type Context = { classes: { id: number; name: string }[]; students: { id: number; class_id: number; anonymous_id: string }[] };
type Job = { id: number; status: string; events: { stage: string; detail: string }[]; results: Record<string, unknown>[] };

export const radarValues = (items: Summary[]) => items.map((item) => item.lower_median_level ?? item.level ?? null);
const get = <T,>(path: string) => fetch(path).then(async (response) => {
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
});
const coverage = (item: Summary) => `${item.assessed_count ?? 0}/${item.skill_count ?? 0}`;

function Chart({ option, onClick }: { option: echarts.EChartsOption; onClick?: (value: unknown) => void }) {
  const node = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!node.current || !node.current.clientWidth) return;
    const chart = echarts.init(node.current);
    chart.setOption(option);
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    if (onClick) chart.on("click", (event) => onClick(event.data));
    return () => { window.removeEventListener("resize", resize); chart.dispose(); };
  }, [option, onClick]);
  return <div className="chart" ref={node} aria-label="数据图表" />;
}

function Radar({ summaries }: { summaries: Summary[] }) {
  const values = radarValues(summaries);
  return <Chart option={{
    tooltip: { formatter: (point) => {
      const index = (point as { dataIndex?: number }).dataIndex ?? 0;
      const item = summaries[index] ?? summaries[0];
      return `${item?.name ?? ""}<br/>等级：${values[index] ?? "未评估"}<br/>覆盖：${item ? coverage(item) : "0/0"}`;
    } },
    radar: { indicator: summaries.map((item) => ({ name: item.name, max: 6 })) },
    series: [{ type: "radar", data: [{ value: values.map((value) => value ?? 0), name: "下中位等级" }] }],
  }} />;
}

function Admin({ school, selectClass, selectStudent }: { school: any; selectClass: (id: number) => void; selectStudent: (id: number) => void }) {
  if (!school) return <p>正在加载学校看板…</p>;
  const heatmap = school.class_heatmap ?? [];
  const heatData = heatmap.flatMap((row: any, y: number) => row.competencies.map((item: Summary, x: number) => ({ value: [x, y, item.level ?? 0], classId: row.class.id })));
  return <section><h1>学校总览</h1><div className="dashboard-grid">
    <article><h2>九项素养</h2><Radar summaries={school.competencies ?? []} /></article>
    <article><h2>班级 × 素养热力图</h2><Chart onClick={(data: any) => data?.classId && selectClass(data.classId)} option={{ tooltip: {}, xAxis: { type: "category", data: (school.competencies ?? []).map((x: Summary) => x.name) }, yAxis: { type: "category", data: heatmap.map((x: any) => x.class.name) }, visualMap: { min: 0, max: 6, calculable: true }, series: [{ type: "heatmap", data: heatData }] }} /></article>
    <article><h2>等级分布</h2><Chart option={{ xAxis: { type: "category", data: (school.level_distribution ?? []).map((x: any) => `L${x.level}`) }, yAxis: { type: "value" }, series: [{ type: "bar", data: (school.level_distribution ?? []).map((x: any) => x.count) }] }} /></article>
    <article><h2>覆盖率</h2><p className="metric">{school.coverage?.assessed_count ?? 0}/{school.coverage?.skill_count ?? 0}（{Math.round((school.coverage?.coverage ?? 0) * 100)}%）</p><h2>评估趋势</h2><Chart option={{ xAxis: { type: "category", data: (school.trend ?? []).map((x: any) => x.date) }, yAxis: { type: "value" }, series: [{ type: "line", data: (school.trend ?? []).map((x: any) => x.assessed_count) }] }} /></article>
  </div><p>点击热力图进入教师视图；在教师矩阵中点击学生进入个人页。</p><button onClick={() => selectStudent(1)}>查看学生示例</button></section>;
}

function Teacher({ context, classId, setClassId, openStudent, skills }: { context: Context; classId: number; setClassId: (value: number) => void; openStudent: (id: number) => void; skills: any[] }) {
  const [dashboard, setDashboard] = useState<any>();
  const [studentId, setStudentId] = useState<number>(0);
  const [evidenceType, setEvidenceType] = useState("teacher_observation");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File>();
  const [evidenceRefs, setEvidenceRefs] = useState<number[]>([]);
  const [skillCode, setSkillCode] = useState("");
  const [job, setJob] = useState<Job>();
  const [error, setError] = useState("");
  const [nextStep, setNextStep] = useState("");
  useEffect(() => { if (classId) get<any>(`/api/classes/${classId}/dashboard`).then((value) => { setDashboard(value); setStudentId(value.students?.[0]?.id ?? 0); }).catch((e) => setError(String(e))); }, [classId]);
  const refreshJob = (id: number) => get<Job>(`/api/assessment-jobs/${id}`).then((value) => { setJob(value); return value; }).catch((e) => { setError(String(e)); throw e; });
  const submitEvidence = async (event: React.FormEvent) => {
    event.preventDefault(); setError("");
    const body = new FormData(); body.set("student_id", String(studentId)); body.set("evidence_type", evidenceType); body.set("text", text); if (file) body.set("file", file);
    try { const evidence = await fetch("/api/evidence", { method: "POST", body }).then(async (response) => { if (!response.ok) throw new Error(await response.text()); return response.json(); }); setEvidenceRefs((value) => [...value, evidence.id]); setText(""); setFile(undefined); } catch (e) { setError(String(e)); }
  };
  const createJob = async () => {
    try {
      const created = await fetch("/api/assessment-jobs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ student_id: studentId, skill_code: skillCode, evidence_refs: evidenceRefs }) }).then(async (response) => { if (!response.ok) throw new Error(await response.text()); return response.json(); });
      setJob(created); const source = new EventSource(`/api/assessment-jobs/${created.id}/events`); const timer = window.setInterval(() => refreshJob(created.id).then((value) => { if (value.status === "succeeded" || value.status === "failed") { window.clearInterval(timer); source.close(); } }).catch(() => {}), 500); source.addEventListener("status", () => refreshJob(created.id).then((value) => { if (value.status === "succeeded" || value.status === "failed") { window.clearInterval(timer); source.close(); } }).catch(() => {})); source.onerror = () => source.close();
    } catch (e) { setError(String(e)); }
  };
  const revise = async () => {
    const current = job?.results.at(-1); if (!current || !nextStep) return;
    try { const updated = await fetch(`/api/assessments/${current.id}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ ...current, next_step: nextStep }) }).then(async (response) => { if (!response.ok) throw new Error(await response.text()); return response.json(); }); setJob(updated); } catch (e) { setError(String(e)); }
  };
  const classStudents = context.students.filter((item) => item.class_id === classId);
  return <section><h1>教师工作台</h1><label>班级 <select value={classId} onChange={(e) => setClassId(Number(e.target.value))}>{context.classes.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
    <div className="matrix">{(dashboard?.students ?? classStudents).map((student: any) => <button key={student.id} onClick={() => openStudent(student.id)}><b>{student.anonymous_id}</b><span>{(student.competencies ?? []).map((item: Summary) => `${item.name} ${item.level ?? "–"}`).join(" · ")}</span></button>)}</div>
    <form onSubmit={submitEvidence}><h2>证据录入</h2><label>学生 <select value={studentId} onChange={(e) => setStudentId(Number(e.target.value))}>{classStudents.map((item) => <option key={item.id} value={item.id}>{item.anonymous_id}</option>)}</select></label><label>证据类型 <select value={evidenceType} onChange={(e) => setEvidenceType(e.target.value)}><option value="teacher_observation">教师观察</option><option value="student_self_reflection">学生自评</option><option value="student_work">学生作品</option></select></label><textarea required value={text} onChange={(e) => setText(e.target.value)} placeholder="输入模拟测试证据" /><input type="file" onChange={(e) => setFile(e.target.files?.[0])} /><button>保存证据</button></form>
    <h2>创建评估任务</h2><label>技能 <select value={skillCode} onChange={(e) => setSkillCode(e.target.value)}><option value="">请选择</option>{skills.map((skill) => <option key={skill.code} value={skill.code}>{skill.code} · {skill.name}</option>)}</select></label><button disabled={!studentId || !skillCode || !evidenceRefs.length} onClick={createJob}>创建 Job</button>
    {job && <article><h2>任务 #{job.id}：{job.status}</h2><p>{job.events.map((event) => `${event.stage}: ${event.detail}`).join(" · ")}</p>{job.results.map((result, index) => <p key={String(result.id)}>修订 {String(result.revision ?? index + 1)}：等级 {String(result.level ?? "未评估")}；{String(result.rationale ?? "")}</p>)}<input aria-label="人工修订建议" value={nextStep} onChange={(e) => setNextStep(e.target.value)} placeholder="人工修订下一步建议" /><button onClick={revise} disabled={!nextStep}>按 result id 人工修订</button></article>}{error && <p role="alert">{error}</p>}
  </section>;
}

function Student({ context, studentId, setStudentId }: { context: Context; studentId: number; setStudentId: (value: number) => void }) {
  const [profile, setProfile] = useState<any>();
  useEffect(() => { if (studentId) get<any>(`/api/students/${studentId}/profile`).then(setProfile); }, [studentId]);
  return <section><h1>我的成长档案</h1><label>模拟学生 <select value={studentId} onChange={(e) => setStudentId(Number(e.target.value))}>{context.students.map((item) => <option key={item.id} value={item.id}>{item.anonymous_id}</option>)}</select></label>{profile && <><Radar summaries={profile.competencies ?? []} /><h2>36 项技能</h2><div className="skills">{profile.skills.map((skill: any) => <article key={skill.code}><b>{skill.code} · {skill.name}</b><span>{skill.result?.status === "assessed" ? `等级 ${skill.result.level}` : "待收集证据"}</span></article>)}</div><h2>证据时间线</h2><ol>{profile.evidence_timeline.map((item: any) => <li key={item.id}>{item.created_at} · {item.evidence_type} · {item.text || item.filename}</li>)}</ol><h2>下一步建议</h2><p>{profile.skills.map((item: any) => item.result?.next_step).find(Boolean) ?? "收集一个具体学习例子。"}</p></>}</section>;
}

export default function App() {
  const [role, setRole] = useState<Role>("管理员"); const [context, setContext] = useState<Context>({ classes: [], students: [] }); const [school, setSchool] = useState<any>(); const [rubric, setRubric] = useState<any>(); const [classId, setClassId] = useState(1); const [studentId, setStudentId] = useState(1);
  useEffect(() => { get<Context>("/api/demo/context").then((value) => { setContext(value); setClassId(value.classes[0]?.id ?? 0); setStudentId(value.students[0]?.id ?? 0); }); get<any>("/api/rubrics/current").then(setRubric); get<any>("/api/dashboard/school").then(setSchool); }, []);
  const skills = rubric?.competencies?.flatMap((item: any) => item.skills) ?? [];
  const openClass = (id: number) => { setClassId(id); setRole("教师"); }; const openStudent = (id: number) => { setStudentId(id); setRole("学生"); };
  return <><header className="notice"><strong>模拟测试数据 / AI 自动评估 / 非正式成绩</strong><span>角色切换不是认证，不代表真实身份或权限。</span></header><nav aria-label="角色切换">{(["管理员", "教师", "学生"] as Role[]).map((item) => <button key={item} className={role === item ? "active" : ""} onClick={() => setRole(item)}>{item}</button>)}</nav><main>{role === "管理员" && <Admin school={school} selectClass={openClass} selectStudent={openStudent} />}{role === "教师" && <Teacher context={context} classId={classId} setClassId={setClassId} openStudent={openStudent} skills={skills} />}{role === "学生" && <Student context={context} studentId={studentId} setStudentId={setStudentId} />}</main></>;
}
