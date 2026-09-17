"""Ten-capability portfolio views grounded in the school rubric and V2 records."""
import json
from collections import Counter
from .database import connect
from .dashboard_v2 import _median
from .competency_demo import STAGES

STAGE_OPTIONS = [{'value': 'latest', 'label': '最新表现'}, {'value': 'baseline', 'label': '起点观察 · 9月1日'}, {'value': 'midpoint', 'label': '阶段观察 · 9月8日'}]
CUTOFF = {'latest': None, 'baseline': STAGES[0], 'midpoint': STAGES[1]}
SHORT_NAMES = {'YY.G01': '关怀者', 'YY.G02': '创造者', 'YY.G03': '学习者'}


def summarize_capability(results):
    known = [r for r in results if r]
    exact = [r for r in known if r['score_state'] == 'exact']
    assessed = [r for r in known if r['score_state'] in {'exact', 'bounded'}]
    counts = Counter(r['score_state'] for r in known)
    if counts['needs_review']:
        state = 'needs_review'
    elif not assessed:
        state = 'insufficient_evidence'
    elif counts['bounded']:
        state = 'bounded'
    elif any(r.get('target_status') == 'below_target' for r in exact):
        state = 'developing'
    elif len(exact) < len(results):
        state = 'partial'
    elif all(r.get('target_status') == 'above_target' for r in exact):
        state = 'above_target'
    elif all(r.get('target_status') in {'above_target', 'meets_target'} for r in exact):
        state = 'meets_target'
    else:
        state = 'partial'
    return {'state': state, 'median_level': _median([r.get('attained_level') for r in exact]),
            'recorded_count': len(known), 'assessed_count': len(assessed), 'skill_count': len(results),
            'coverage': len(assessed)/len(results) if results else 0,
            'target_met_count': sum(r.get('target_status') in {'above_target', 'meets_target'} for r in exact),
            'missing_count': len(results)-len(assessed), 'review_count': counts['needs_review']}


def _load(connection, stage):
    if stage not in CUTOFF:
        raise ValueError('invalid stage')
    goals = []
    for gid, code, name in connection.execute("""SELECT g.id,g.code,g.name FROM education_goals_v2 g JOIN rubric_versions_v2 r ON r.id=g.rubric_id WHERE r.code='kai_feng_yuyang_260910' ORDER BY g.code"""):
        caps = []
        for cid, ccode, cname in connection.execute('SELECT id,code,name FROM capabilities_v2 WHERE goal_id=? ORDER BY code', (gid,)).fetchall():
            skills = [{'code': s, 'name': n} for s,n in connection.execute('SELECT code,name_cn FROM skills_v2 WHERE capability_id=? ORDER BY code', (cid,))]
            caps.append({'code': ccode, 'name': cname, 'goal_code': code, 'goal_name': SHORT_NAMES[code], 'skills': skills})
        goals.append({'code': code, 'name': name, 'short_name': SHORT_NAMES[code], 'capabilities': caps})
    cutoff = CUTOFF[stage]
    rows = connection.execute("""SELECT j.id,j.student_id,j.skill_code,j.context,j.period,j.created_at,j.config_snapshot,j.evidence_refs,
          r.id,r.result,r.engine,r.revision FROM assessment_jobs_v2 j JOIN assessment_results_v2 r ON r.job_id=j.id
          WHERE j.status='succeeded' AND j.rubric_code='kai_feng_yuyang_260910'
          AND r.revision=(SELECT MAX(revision) FROM assessment_results_v2 WHERE job_id=j.id)
          AND (? IS NULL OR substr(j.created_at,1,10)<=?)
          ORDER BY CASE WHEN r.engine='seed_demo_v2' THEN 0 WHEN r.engine='seed_kanban_v1' THEN 1 ELSE 2 END,j.created_at,j.id""", (cutoff, cutoff)).fetchall()
    latest, history = {}, {}
    for jid,sid,code,context,period,date,config,refs,rid,payload,engine,revision in rows:
        result = json.loads(payload)
        result.pop('judgments', None)
        result.update(id=rid,job_id=jid,engine=engine,revision=revision,created_at=date,context=context,period=period,
                      config_id=json.loads(config)['id'],evidence_refs=json.loads(refs))
        latest[(sid,code)] = result
        history.setdefault((sid,code),[]).append(result)
    return goals, latest, history


def _student(student, goals, latest):
    sid,name,cid,cname,simulated=student
    capabilities=[]
    goal_summaries=[]
    for goal in goals:
        members=[]
        for cap in goal['capabilities']:
            results=[latest.get((sid,s['code'])) for s in cap['skills']]
            summary=summarize_capability(results)
            capabilities.append({k:v for k,v in cap.items() if k!='skills'} | summary)
            members.extend(results)
        goal_summaries.append({'code':goal['code'],'name':goal['name'],'short_name':goal['short_name'],**summarize_capability(members)})
    return {'id':sid,'anonymous_id':name,'class_id':cid,'class_name':cname,'is_simulated_test_data':bool(simulated),
            'capabilities':capabilities,'goals':goal_summaries}


def board(class_id=None, name='', stage='latest'):
    with connect() as c:
        goals,latest,_=_load(c,stage)
        students=[_student(s,goals,latest) for s in c.execute('''SELECT s.id,s.anonymous_id,cl.id,cl.name,s.is_simulated_test_data FROM students s JOIN classes cl ON cl.id=s.class_id WHERE (? IS NULL OR cl.id=?) ORDER BY s.id''',(class_id,class_id)) if name.casefold() in s[1].casefold()]
    counts=Counter(cap['state'] for s in students for cap in s['capabilities'])
    return {'goals':goals,'students':students,'stage':stage,'stages':STAGE_OPTIONS,'state_counts':dict(counts),
            'summary':{'student_count':len(students),'recorded_skills':sum(cap['recorded_count'] for s in students for cap in s['capabilities']),
                       'missing_skills':sum(cap['missing_count'] for s in students for cap in s['capabilities']),
                       'review_skills':sum(cap['review_count'] for s in students for cap in s['capabilities'])},
            'methodology':'素养展示已形成点分技能的较低中位 Level，并同时显示覆盖率；全部技能有明确评分且达到各自目标才点亮。区间与缺证不填零，不按历史最高值覆盖最新表现。',
            'data_notice':'模拟测试数据 / AI自动评估 / 非正式成绩；演示配置未校准'}


def profile(student_id, stage='latest', capability_code=None):
    with connect() as c:
        student=c.execute('SELECT s.id,s.anonymous_id,cl.id,cl.name,s.is_simulated_test_data FROM students s JOIN classes cl ON cl.id=s.class_id WHERE s.id=?',(student_id,)).fetchone()
        if not student:
            return None
        goals,latest,history=_load(c,stage)
        output=_student(student,goals,latest)
        if capability_code is None:
            return output
        cap=next((a for g in goals for a in g['capabilities'] if a['code']==capability_code),None)
        if cap is None:
            return None
        skills=[]
        for skill in cap['skills']:
            result=latest.get((student_id,skill['code']))
            records=history.get((student_id,skill['code']),[])
            comparable=[r for r in records if result and (r['config_id'],r.get('scoring_version'),r['context'])==(result['config_id'],result.get('scoring_version'),result['context'])]
            evidence=[]
            for ref in result['evidence_refs'] if result else []:
                row=c.execute('SELECT id,text,evidence_type,created_at FROM evidence WHERE id=? AND student_id=?',(ref,student_id)).fetchone()
                if row:
                    evidence.append(dict(zip(('id','text','evidence_type','created_at'),row)))
            levels=[{'level':level,'descriptors':json.loads(desc)} for level,desc in c.execute("""SELECT l.level,l.descriptors FROM levels_v2 l JOIN skills_v2 s ON s.id=l.skill_id JOIN rubric_versions_v2 r ON r.id=s.rubric_id WHERE s.code=? AND r.code='kai_feng_yuyang_260910' ORDER BY l.level""",(skill['code'],))]
            skills.append(skill | {'result':result,'history':comparable,'excluded_incomparable_count':len(records)-len(comparable),'evidence':evidence,'levels':levels})
        return {'student':{'id':student_id,'name':student[1]},'capability':next(a for a in output['capabilities'] if a['code']==capability_code),'skills':skills}
