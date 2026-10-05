import { useEffect, useMemo, useRef, useState } from 'react';
import * as echarts from 'echarts';
import './competency-board.css';

type State = 'partial'|'developing'|'bounded'|'needs_review'|'insufficient_evidence'|'meets_target'|'above_target';
type Summary = {code:string;name:string;goal_code?:string;goal_name?:string;short_name?:string;state:State;median_level:number|null;recorded_count:number;assessed_count:number;skill_count:number;coverage:number;missing_count:number;review_count:number;target_met_count:number};
type Profile = {id:number;anonymous_id:string;class_id:number;class_name:string;capabilities:Summary[];goals:Summary[]};
type Goal = {code:string;name:string;short_name:string;capabilities:Summary[]};
type CohortCapability = Pick<Summary,'code'|'name'|'goal_code'|'goal_name'|'median_level'|'coverage'|'assessed_count'|'skill_count'> & {contributing_students:number};
type Cohort = {student_count:number;capabilities:CohortCapability[]};
type Board = {goals:Goal[];students:Profile[];cohort:Cohort;stages:{value:string;label:string}[];methodology:string;summary:{student_count:number;recorded_skills:number;missing_skills:number;review_skills:number}};
type Result = {score_state:string;score_display:number|null;score_lower:number|null;score_upper:number|null;attained_level:number|null;target_gap:number|null;target_level:number;target_version:string;scoring_config_version:number;engine:string;job_id:number;revision:number;created_at:string;feedback:string;context:string};
type SkillDetail = {code:string;name:string;result:Result|null;history:Result[];excluded_incomparable_count:number;evidence:{id:number;text:string;evidence_type:string;created_at:string}[];levels:{level:number;descriptors:string[]}[]};
type Detail = {student:{id:number;name:string};capability:Summary;skills:SkillDetail[]};
export const stateLabels:Record<State,string> = {partial:'部分已评',developing:'发展中',bounded:'存在区间',needs_review:'待复核',insufficient_evidence:'待补证',meets_target:'达到目标',above_target:'超过目标'};
const short = (code:string) => ({'YY.G01':'关怀者','YY.G02':'创造者','YY.G03':'学习者'}[code]);
const pct = (x:number)=>`${Math.round(x*100)}%`;
async function read<T>(url:string,signal?:AbortSignal):Promise<T>{const response=await fetch(url,{signal});if(!response.ok)throw new Error(`读取失败（${response.status}）`);return response.json();}
function useRead<T>(url:string){const [value,setValue]=useState<T>();const [error,setError]=useState('');const [loading,setLoading]=useState(true);useEffect(()=>{const c=new AbortController();setValue(undefined);setError('');setLoading(true);read<T>(url,c.signal).then(v=>{if(!c.signal.aborted)setValue(v);}).catch(e=>{if(!c.signal.aborted)setError(String(e));}).finally(()=>{if(!c.signal.aborted)setLoading(false);});return()=>c.abort();},[url]);return {value,error,loading};}
const level=(c:Summary)=>c.median_level==null?'—':`L${c.median_level}`;
const score=(r:Result|null)=>!r?'暂无记录':r.score_state==='exact'?`${r.score_display} 分`:r.score_state==='bounded'?`[${r.score_lower}, ${r.score_upper}]` : r.score_state==='needs_review'?'待复核':'证据不足';

export function tenCapabilityOption(caps:Summary[]):echarts.EChartsOption {
  const valid=caps.filter(c=>c.median_level!=null);
  // Polar bars leave unknown axes blank; a filled radar polygon would imply zero at those axes.
  return {animation:false,tooltip:{trigger:'item'},polar:{radius:['12%','72%']},
    angleAxis:{type:'category',data:caps.map(c=>c.name),startAngle:90,axisLabel:{fontSize:11,color:'#37586b'}},
    radiusAxis:{min:0,max:6,interval:1,axisLabel:{color:'#687780'},splitLine:{lineStyle:{color:'#e0e7ed'}}},
    series:[{type:'bar',coordinateSystem:'polar',roundCap:true,data:caps.map(c=>c.median_level==null?{value:null}:{value:c.median_level,itemStyle:{color:c.goal_code==='YY.G01'?'#bd8733':c.goal_code==='YY.G02'?'#3475a5':'#248980'}}),name:'已评技能中位 Level'}],
    graphic:valid.length?[]:[{type:'text',left:'center',top:'middle',style:{text:'等待证据',fill:'#687780'}}]};
}

function TenChart({capabilities}:{capabilities:Summary[]}){
 const node=useRef<HTMLDivElement>(null);const option=useMemo(()=>tenCapabilityOption(capabilities),[capabilities]);
 useEffect(()=>{if(!node.current?.clientWidth)return;const chart=echarts.init(node.current);chart.setOption(option);const resize=()=>chart.resize();const observer=new ResizeObserver(resize);observer.observe(node.current);return()=>{observer.disconnect();chart.dispose();};},[option]);
 return <div className="ten-chart" ref={node} role="img" aria-label="10项核心素养画像，空白维度表示暂无明确点分"/>;
}

export function cohortRadarOption(capabilities:CohortCapability[]):echarts.EChartsOption {
 const complete=capabilities.length===10&&capabilities.every(c=>c.median_level!=null);
 return {animation:false,tooltip:{trigger:'item'},radar:{radius:'58%',splitNumber:6,
  indicator:capabilities.map(c=>({name:`${c.goal_name}\n${c.name}`,max:6,min:0,color:c.goal_code==='YY.G01'?'#996922':c.goal_code==='YY.G02'?'#3475a5':'#248980'})),
  axisName:{fontSize:11},axisLine:{lineStyle:{color:'#d4e0e7'}},splitLine:{lineStyle:{color:'#d4e0e7'}},splitArea:{areaStyle:{color:['#fff','#f5f9fb']}}},
  // Do not feed null into ECharts radar: it can render missing values at the origin.
  series:complete?[{type:'radar',name:'群体中位 Level',symbolSize:6,lineStyle:{width:2,color:'#3475a5'},itemStyle:{color:'#3475a5'},areaStyle:{color:'#3475a5',opacity:.12},data:[{name:'群体中位 Level（非总分）',value:capabilities.map(c=>c.median_level!)}]}]:[],
  graphic:complete?[]:[{type:'text',left:'center',top:'middle',style:{text:'部分维度暂无明确水平\n已知值见右侧明细，不补零连线',fill:'#607686',fontSize:12,align:'center',lineHeight:22}}]};
}

function CohortRadar({cohort,className,stageLabel}:{cohort:Cohort;className:string;stageLabel:string}){
 const node=useRef<HTMLDivElement>(null);const option=useMemo(()=>cohortRadarOption(cohort.capabilities),[cohort.capabilities]);
 useEffect(()=>{if(!node.current?.clientWidth)return;const chart=echarts.init(node.current);chart.setOption(option);const observer=new ResizeObserver(()=>chart.resize());observer.observe(node.current);return()=>{observer.disconnect();chart.dispose();};},[option]);
 return <section className="cohort-radar" aria-label="整体学生素养雷达图"><header className="section-heading"><div><h2>{className} · 整体学生素养雷达图</h2><p>{cohort.student_count} 名学生 · {stageLabel} · 10项核心素养</p></div><div className="cohort-goal-legend"><span>关怀者 · 3项</span><span>创造者 · 4项</span><span>学习者 · 3项</span></div></header>
 <div className="cohort-radar-layout"><div className="cohort-chart" ref={node} role="img" aria-label="全体学生10项核心素养雷达图，刻度Level 1至6，具体数值见明细表"/><div className="cohort-table-scroll"><table aria-label="整体素养雷达明细"><thead><tr><th>育人目标 / 素养</th><th>中位 Level</th><th>有效人数</th><th>技能覆盖</th></tr></thead><tbody>{cohort.capabilities.map(c=><tr key={c.code}><th><small>{c.goal_name}</small>{c.name}</th><td>{c.median_level==null?'暂无明确水平':`L${c.median_level}`}</td><td>{c.contributing_students}/{cohort.student_count}</td><td>{pct(c.coverage)}<small>{c.assessed_count}/{c.skill_count}</small></td></tr>)}</tbody></table></div></div>
 <p className="method-note">每项先取学生已评点分技能的较低中位 Level，再取学生之间的较低中位 Level；有效人数指该维度有明确 Level 的学生数。覆盖率包含点分与区间；缺证、冲突和区间不折算为点分。只随班级和观察阶段变化，不受学生搜索、育人目标或状态筛选影响。不计算总分或排名，图形面积不代表整体优劣。</p></section>;
}

function ProfileContent({profile,onCapability}:{profile:Profile;onCapability:(code:string)=>void}){
 return <><div className="identity-goals">{profile.goals.map(g=><section key={g.code} className={`identity-goal ${g.code}`}><small>{g.name}</small><h3>{g.short_name??short(g.code)}</h3><strong>{level(g)}</strong><p>{g.assessed_count}/{g.skill_count} 技能有评分 · 覆盖 {pct(g.coverage)}</p></section>)}</div>
 <div className="ten-profile"><TenChart capabilities={profile.capabilities}/><div className="ten-cards" aria-label="10项核心素养详情">{profile.capabilities.map(c=><button key={c.code} onClick={()=>onCapability(c.code)} className={`capability-tile ${c.state}`}><small>{c.goal_name}</small><b>{c.name}</b><span>{level(c)} · {stateLabels[c.state]}</span><small>已评 {c.assessed_count}/{c.skill_count} · 达到目标 {c.target_met_count}/{c.skill_count}</small></button>)}</div></div></>;
}

function CapabilityDialog({studentId,code,stage,onClose}:{studentId:number;code:string;stage:string;onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null);const {value,error,loading}=useRead<Detail>(`/api/v2/students/${studentId}/capabilities/${code}?stage=${stage}`);
 useEffect(()=>{dialog.current?.showModal();},[]);
 return <dialog ref={dialog} className="capability-dialog" onClose={onClose} aria-label="素养证据详情"><form method="dialog"><button aria-label="关闭素养详情">关闭 ×</button></form>{loading?<p>正在读取量规与证据…</p>:error?<p role="alert">{error}</p>:value&&<><small>{value.student.name} · {value.capability.goal_name}</small><h2>{value.capability.name}</h2><p>{stateLabels[value.capability.state]} · 已评 {value.capability.assessed_count}/{value.capability.skill_count} 个技能</p>{value.skills.map(skill=><section className="detail-skill" key={skill.code}><header><div><small>{skill.code}</small><h3>{skill.name}</h3></div><strong>{score(skill.result)}</strong></header>{skill.result&&<><p>完整水平 {skill.result.attained_level?`Level ${skill.result.attained_level}`:'尚未确定'} · 任务目标 Level {skill.result.target_level} · {skill.result.engine.startsWith('seed_')?'模拟种子数据':skill.result.engine==='manual_revision'?'人工修订':'评估结果'}</p><p>{skill.result.feedback}</p></>}
 <details open={skill.evidence.length>0}><summary>证据与情境（{skill.evidence.length}）</summary>{skill.evidence.length?skill.evidence.map(e=><blockquote key={e.id}><small>证据 #{e.id} · {e.created_at.slice(0,10)} · {e.evidence_type}</small><p>{e.text}</p></blockquote>):<p>暂无关联证据，可在评价任务中补充。</p>}</details>
 <details><summary>学校量规 Level 1–6</summary>{skill.levels.map(l=><div key={l.level}><b>Level {l.level}</b><ul>{l.descriptors.map((d,i)=><li key={i}>{d}</li>)}</ul></div>)}</details>
 <details open={skill.history.length>1}><summary>可比成长记录（{skill.history.length}）</summary><p>同技能、同评分配置、同情境。区间独立呈现，修订保留为同一次观察。</p><ol className="stage-timeline">{skill.history.map(r=><li key={r.job_id}><time>{r.created_at.slice(0,10)}</time><b>{score(r)}</b><span>{r.context} · 修订 {r.revision}</span></li>)}</ol>{skill.excluded_incomparable_count>0&&<p>另有 {skill.excluded_incomparable_count} 条不同版本或情境记录，不连接为同一趋势。</p>}</details></section>)}</>}</dialog>;
}

export function StudentCompetencies({studentId,refreshKey=0}:{studentId:number;refreshKey?:number}){
 const {value,error}=useRead<Profile>(`/api/v2/students/${studentId}/competency-profile?refresh=${refreshKey}`);const [selected,setSelected]=useState<string>();
 return <section className="student-competency-module"><h2>10项核心素养 · 三个育人目标</h2><p className="method-note">中位 Level 描述已评技能，覆盖不足不代表整项素养已达标；未知维度留空。</p>{error?<p role="alert">{error}</p>:value?<ProfileContent profile={value} onCapability={setSelected}/>:<p>正在加载核心素养…</p>}{selected&&<CapabilityDialog studentId={studentId} code={selected} stage="latest" onClose={()=>setSelected(undefined)}/>}</section>;
}

export default function CompetencyBoard({context,openStudent}:{context?:{classes:{id:number;name:string}[]};openStudent:(id:number)=>void}){
 const [classId,setClassId]=useState('');const [name,setName]=useState('');const [stage,setStage]=useState('latest');const [goal,setGoal]=useState('');const [state,setState]=useState('');const [mentor,setMentor]=useState(false);const [showSummary,setShowSummary]=useState(false);
 const [compare,setCompare]=useState<number[]>([]);const [selected,setSelected]=useState<{id:number;code:string}>();const [activeId,setActiveId]=useState<number>();
 const query=new URLSearchParams({stage,name});if(classId)query.set('class_id',classId);
 const {value,error,loading}=useRead<Board>(`/api/v2/competency-board?${query}`);
 const goals=(value?.goals??[]).filter(g=>!goal||g.code===goal);const caps=goals.flatMap(g=>g.capabilities);
 const students=(value?.students??[]).filter(s=>!state||s.capabilities.some(c=>(!goal||c.goal_code===goal)&&c.state===state));
 const active=students.find(s=>s.id===activeId);const compared=students.filter(s=>compare.includes(s.id));
 const toggled=(id:number)=>setCompare(current=>current.includes(id)?current.filter(x=>x!==id):current.length<2?[...current,id]:current);
 return <div className="page competency-board"><header className="overview-heading"><div><small>凯风雨旸小学 · 学习过程与证据</small><h1>学生素养成长看板</h1><p>20名模拟学生，10项核心素养，三个育人目标</p></div><div className="board-actions"><button aria-pressed={mentor} onClick={()=>setMentor(!mentor)}>{mentor?'返回全体看板':'导师关注视图'}</button><button aria-expanded={showSummary} onClick={()=>setShowSummary(!showSummary)}>学情摘要</button></div></header>
 <section className="board-filters" aria-label="素养看板筛选"><label>班级<select aria-label="班级" value={classId} onChange={e=>{setClassId(e.target.value);setCompare([]);setActiveId(undefined);}}><option value="">全部班级</option>{context?.classes.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>观察阶段<select aria-label="观察阶段" value={stage} onChange={e=>setStage(e.target.value)}><option value="latest">最新表现</option><option value="baseline">起点观察 · 9月1日</option><option value="midpoint">阶段观察 · 9月8日</option></select></label><label>育人目标<select aria-label="育人目标" value={goal} onChange={e=>setGoal(e.target.value)}><option value="">三个育人目标</option>{value?.goals.map(g=><option key={g.code} value={g.code}>{g.short_name}</option>)}</select></label><label>素养状态<select aria-label="素养状态" value={state} onChange={e=>setState(e.target.value)}><option value="">全部状态</option>{Object.entries(stateLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label>学生搜索<input placeholder="搜索匿名学生" value={name} onChange={e=>setName(e.target.value)}/></label><button onClick={()=>{setClassId('');setName('');setStage('latest');setGoal('');setState('');setCompare([]);}}>重置筛选</button></section>
 {loading?<p role="status">正在读取素养看板…</p>:error?<p role="alert">{error}</p>:value&&<><div className="board-stats"><span><b>{students.length}</b> 当前学生</span><span><b>10</b> 核心素养</span><span><b>38</b> 量规技能</span><span><b>{value.summary.review_skills}</b> 待复核技能</span></div>
 <p className="method-note">{value.methodology}</p>
 {value.cohort&&<CohortRadar cohort={value.cohort} className={context?.classes.find(c=>String(c.id)===classId)?.name??'全校'} stageLabel={value.stages.find(s=>s.value===stage)?.label??'最新表现'}/>}
 {showSummary&&<section className="board-summary"><h2>当前筛选学情摘要</h2><p>当前展示 {students.length} 名学生；{students.reduce((n,s)=>n+s.capabilities.reduce((m,c)=>m+c.assessed_count,0),0)} 个学生技能已有点分或区间。建议先处理冲突，再补充尚未观察的技能证据。</p><ul>{goals.map(g=><li key={g.code}>{g.short_name}：{g.capabilities.map(c=>c.name).join('、')}</li>)}</ul><p>本摘要来自后端统计，不调用外部模型。</p></section>}
 <div className="state-legend">{Object.entries(stateLabels).map(([key,label])=><span className={key} key={key}>{label}</span>)}</div>
 {!students.length?<p className="empty-state">没有符合筛选条件的学生，请调整筛选。</p>:mentor?<section className="mentor-list"><h2>导师关注清单</h2><p>按学生编号查看，优先标记待复核与待补证事项。</p>{students.map(s=><article key={s.id}><button onClick={()=>setActiveId(s.id)}>{s.anonymous_id}</button><span>{s.class_name}</span><div>{s.capabilities.filter(c=>(!goal||c.goal_code===goal)&&['needs_review','insufficient_evidence','developing','bounded'].includes(c.state)).map(c=><button key={c.code} className={c.state} onClick={()=>setSelected({id:s.id,code:c.code})}>{c.name} · {stateLabels[c.state]}</button>)}</div></article>)}</section>:<section><div className="section-heading"><h2>学生 × 10项核心素养</h2><p>勾选两名学生并排查看画像 · 已选 {compared.length}/2</p></div><div className="competency-matrix-scroll"><table className="competency-matrix" aria-label="学生十项核心素养矩阵"><thead><tr><th rowSpan={2}>学生 / 对比</th>{goals.map(g=><th className={g.code} key={g.code} colSpan={g.capabilities.length}>{g.short_name}<small>{g.name}</small></th>)}</tr><tr>{caps.map(c=><th key={c.code}>{c.name}</th>)}</tr></thead><tbody>{students.map(s=><tr key={s.id}><th><label><input type="checkbox" aria-label={`对比${s.anonymous_id}`} checked={compare.includes(s.id)} disabled={!compare.includes(s.id)&&compare.length>=2} onChange={()=>toggled(s.id)}/><button onClick={()=>setActiveId(s.id)}>{s.anonymous_id}</button></label><small>{s.class_name}</small></th>{caps.map(c=>{const item=s.capabilities.find(a=>a.code===c.code)!;return <td key={c.code}><button className={`matrix-cell ${item.state}`} aria-label={`${s.anonymous_id} ${c.name} ${stateLabels[item.state]}`} onClick={()=>setSelected({id:s.id,code:c.code})}><b>{level(item)}</b><span>{stateLabels[item.state]}</span><small>{item.assessed_count}/{item.skill_count} 技能</small></button></td>;})}</tr>)}</tbody></table></div></section>}
 {compared.length>0&&<section className="profile-comparison"><h2>并排画像对比</h2><p>仅比较各项水平与证据覆盖，不计算总分或名次。</p><div>{compared.map(s=><article key={s.id}><h3>{s.anonymous_id}</h3><TenChart capabilities={s.capabilities}/>{s.capabilities.map(c=><p key={c.code}>{c.name}：{level(c)} · {stateLabels[c.state]} · {c.assessed_count}/{c.skill_count}</p>)}</article>)}</div></section>}
 {active&&<section className="board-person"><header className="section-heading"><h2>{active.anonymous_id} · 10项核心素养画像</h2><button onClick={()=>openStudent(active.id)}>打开完整成长档案</button></header><ProfileContent profile={active} onCapability={code=>setSelected({id:active.id,code})}/></section>}
 </>}{selected&&<CapabilityDialog key={`${selected.id}-${selected.code}-${stage}`} studentId={selected.id} code={selected.code} stage={stage} onClose={()=>setSelected(undefined)}/>}</div>;
}
