"""Repeatable classroom portfolio fixtures; never calls an external model."""
import json
from .assessment_v2 import score

STAGES = ('2026-09-01', '2026-09-08', '2026-09-15')


def seed_competency_demo(connection):
    from .database import _seed_v2_config

    tasks = [
        ('YY.S03', '小组分歧如何解决', '记录一次分歧，复述同伴想法，并尝试协商。'),
        ('YY.S04', '我们的班级伙伴', '主动邀请同伴加入，分工合作并维系关系。'),
        ('YY.S08', '多语言问候卡', '学习不同语言的问候，说明表达和文化之间的联系。'),
        ('YY.S11', '我是谁的成长手册', '描述自己的兴趣、身份与成长经历。'),
        ('YY.S14', '校园植物探究', '提出一个可探究的问题，说明问题的来源。'),
        ('YY.S19', '节水行动设计', '观察校园用水现象，识别真实问题与设计限制。'),
        ('YY.S22', '给同伴的科学分享', '说明面向谁表达、想传递什么，并选择合适形式。'),
        ('YY.S26', '一周学习计划', '设定学习目标，安排步骤和时间。'),
        ('YY.S31', '故事中的新发现', '从阅读和观察中寻找灵感，记录不同想法。'),
        ('YY.S36', '校园数据小调查', '提出数学问题，用数量关系和数据尝试解答。'),
    ]
    students = connection.execute('SELECT id FROM students WHERE is_simulated_test_data=1 ORDER BY id LIMIT 20').fetchall()
    expanded = []
    for cap_index, (representative, title, behavior) in enumerate(tasks):
        codes = connection.execute("""SELECT sibling.code FROM skills_v2 s JOIN skills_v2 sibling ON sibling.capability_id=s.capability_id JOIN rubric_versions_v2 r ON r.id=s.rubric_id WHERE s.code=? AND r.code='kai_feng_yuyang_260910' ORDER BY sibling.code""", (representative,)).fetchall()
        expanded.extend((cap_index, code, title, behavior, code == representative) for (code,) in codes)
    for cap_index, code, title, behavior, representative in expanded:
        row = connection.execute("""SELECT c.id,c.rubric_id FROM scoring_configs_v2 c
            JOIN rubric_versions_v2 r ON r.id=c.rubric_id
            WHERE r.code='kai_feng_yuyang_260910' AND c.skill_code=?
            AND c.version=1 AND c.is_simulated_test_data=1""", (code,)).fetchone()
        if not row:
            continue
        config = _seed_v2_config(connection, row[0])
        target = {'skill_code': code, 'grade': '3-6', 'term': 'default', 'target_version': 'yy-grade3-6-default-v1', 'target_level': 3, 'basic': 2, 'mastery': 3, 'excellent': 4}
        for (student_id,) in students:
            for stage_index, stage in enumerate(STAGES):
                if not representative and stage_index != 2:
                    continue
                key = f'kanban-v1-{student_id}-{code}-{stage}'
                if connection.execute('SELECT 1 FROM assessment_jobs_v2 WHERE idempotency_key=?', (key,)).fetchone():
                    continue
                pattern = (student_id + cap_index) % 8
                level = min(5, 1 + (student_id + cap_index) % 3 + stage_index)
                kind = ('teacher_observation', 'student_self_reflection', 'student_work')[stage_index]
                evidence_text = f'模拟测试数据｜{title}｜{stage}。{behavior}本记录为界面演示构造的情境样例，指标档位是未校准模拟判断。'
                ref = connection.execute('INSERT INTO evidence (student_id,evidence_type,text,created_at) VALUES (?,?,?,?)', (student_id, kind, evidence_text, stage+' 09:00:00')).lastrowid
                judgments = []
                for group in config['groups']:
                    for indicator in group['indicators']:
                        state = 'observed'
                        value = 4 if group['level'] <= level else (1 + stage_index) if group['level'] == level+1 else 0
                        if pattern == 4 and stage_index == 2:
                            state, value = 'unknown', None
                        elif pattern == 5 and stage_index == 2:
                            state, value = ('conflict', None) if not judgments else ('unknown', None)
                        elif pattern == 3 and stage_index == 2 and group['level'] == level+1:
                            state, value = 'unknown', None
                        if pattern == 6:
                            value = 4 if group['level'] == 1 else 1 if group['level'] == 2 else 0
                        if pattern == 7 and stage_index == 2:
                            value = 4 if group['level'] <= 3 else 0
                        judgments.append({'indicator_id': indicator['database_id'], 'observation_state': state, 'ordinal_score': value, 'evidence_refs': [ref], 'fragment_locator': f'{title} · 模拟情境记录', 'reason': '演示判断，尚未经教研校准', 'support_context': '教师提供任务澄清'})
                result = score(config, judgments, 3, {ref}) | {
                    'judgments': judgments, 'feedback': f'下一步在“{title}”中再次观察：{behavior}',
                    'rubric_code': 'kai_feng_yuyang_260910', 'scoring_config_version': 1,
                    'target_version': target['target_version'], 'model_run_id': key,
                    'is_simulated_test_data': True, 'calibration_status': 'uncalibrated',
                }
                job_id = connection.execute("""INSERT INTO assessment_jobs_v2
                    (student_id,skill_code,evidence_refs,config_snapshot,target_snapshot,rubric_code,
                     context,support_level,period,idempotency_key,status,attempts,created_at,updated_at)
                    VALUES (?,?,?,?,?,'kai_feng_yuyang_260910',?,'教师提供任务澄清','default',?,'succeeded',1,?,?)""",
                    (student_id, code, json.dumps([ref]), json.dumps(config, ensure_ascii=False), json.dumps(target, ensure_ascii=False), title, key, stage+' 09:00:00', stage+' 09:00:00')).lastrowid
                rid = connection.execute("INSERT INTO assessment_results_v2 (job_id,revision,result,engine,created_at) VALUES (?,1,?,'seed_kanban_v1',?)", (job_id, json.dumps(result, ensure_ascii=False), stage+' 09:00:00')).lastrowid
                connection.executemany('INSERT INTO assessment_judgments_v2 (result_id,indicator_id,state,ordinal_score,evidence_refs,fragment_locator,reason,support_context) VALUES (?,?,?,?,?,?,?,?)', [(rid,j['indicator_id'],j['observation_state'],j['ordinal_score'],json.dumps(j['evidence_refs']),j['fragment_locator'],j['reason'],j['support_context']) for j in judgments])
                connection.execute("INSERT INTO job_events_v2 (job_id,stage,detail,created_at) VALUES (?,'succeeded','seed_kanban_v1：模拟阶段证据',?)", (job_id, stage+' 09:00:00'))
