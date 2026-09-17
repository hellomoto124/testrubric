from fastapi.testclient import TestClient
from app.main import app
from app.database import connect, initialize
from app.main import RUBRIC


def test_board_has_twenty_students_ten_capabilities_and_three_goals():
    with TestClient(app) as client:
        response = client.get('/api/v2/competency-board')
        assert response.status_code == 200
        board = response.json()
        assert len(board['students']) == 20
        assert [g['short_name'] for g in board['goals']] == ['关怀者', '创造者', '学习者']
        assert [len(g['capabilities']) for g in board['goals']] == [3, 4, 3]
        assert all(len(s['capabilities']) == 10 for s in board['students'])
        assert all(c['recorded_count'] >= 1 for s in board['students'] for c in s['capabilities'])
        states = {c['state'] for s in board['students'] for c in s['capabilities']}
        assert {'developing', 'meets_target', 'above_target', 'needs_review', 'insufficient_evidence'} <= states
        filtered = client.get('/api/v2/competency-board?class_id=1&name=01').json()
        assert [s['id'] for s in filtered['students']] == [1]
        assert client.get('/api/v2/competency-board?stage=invalid').status_code == 422


def test_profile_exposes_rubric_evidence_and_comparable_history():
    with TestClient(app) as client:
        response = client.get('/api/v2/students/1/competency-profile')
        assert response.status_code == 200
        profile = response.json()
        assert len(profile['capabilities']) == 10
        detail = client.get('/api/v2/students/1/capabilities/YY.C10').json()
        assert len(detail['skills']) == 3
        tracked = next(s for s in detail['skills'] if s['code'] == 'YY.S36')
        assert len(tracked['history']) == 3
        assert len(tracked['levels']) == 6
        assert tracked['evidence'][0]['text'].startswith('模拟测试数据')
        assert tracked['result']['engine'] == 'seed_kanban_v1'
        assert client.get('/api/v2/students/999/competency-profile').status_code == 404
        assert client.get('/api/v2/students/1/capabilities/YY.C99').status_code == 404


def test_seed_is_repeatable_and_does_not_attach_to_real_students():
    with TestClient(app):
        pass
    with connect() as c:
        assert c.execute("SELECT count(*) FROM assessment_results_v2 WHERE engine='seed_kanban_v1'").fetchone()[0] == 1160
        c.execute("INSERT INTO students VALUES (21,1,'非模拟占位',0)")
    initialize(RUBRIC)
    with connect() as c:
        assert c.execute("SELECT count(*) FROM assessment_results_v2 WHERE engine='seed_kanban_v1'").fetchone()[0] == 1160
        assert c.execute('SELECT count(*) FROM assessment_jobs_v2 WHERE student_id=21').fetchone()[0] == 0


def test_capability_is_not_lit_by_one_skill_or_unknown_zero():
    from app.competency_board import summarize_capability
    assert summarize_capability([None, None])['median_level'] is None
    result = {'score_state': 'exact', 'attained_level': 4, 'target_status': 'above_target'}
    assert summarize_capability([result, None])['state'] == 'partial'
    assert summarize_capability([result, result])['state'] == 'above_target'
    uncertain = {'score_state': 'bounded', 'attained_level': 2, 'target_status': 'uncertain'}
    assert summarize_capability([uncertain])['median_level'] is None
    assert summarize_capability([uncertain])['state'] == 'bounded'


def test_live_assessment_beats_seed_in_both_views_after_restart(monkeypatch):
    from app.worker import process_one_job
    monkeypatch.setenv('DEMO_AGENT_MODE', 'true')
    with TestClient(app) as client:
        evidence = client.post('/api/evidence', json={'student_id': 1, 'evidence_type': 'teacher_observation', 'text': '模拟测试数据：新的数学调查情境。'}).json()
        job = client.post('/api/v2/assessment-jobs', json={'student_id': 1, 'skill_code': 'YY.S36', 'evidence_refs': [evidence['id']], 'idempotency_key': 'live-board-test'}).json()
    assert process_one_job()['id'] == job['id']
    initialize(RUBRIC)
    with TestClient(app) as client:
        detail = client.get('/api/v2/students/1/capabilities/YY.C10').json()
        latest = next(s for s in detail['skills'] if s['code'] == 'YY.S36')
        assert latest['result']['engine'] == 'demo_deterministic_v2'
        assert latest['evidence'][0]['id'] == evidence['id']
        # Different task contexts must not be connected into a synthetic growth trend.
        assert len(latest['history']) == 1
        assert latest['excluded_incomparable_count'] == 3
        old_view = client.get('/api/v2/dashboard/student/1').json()
        same = next(s for g in old_view['goals'] for c in g['capabilities'] for s in c['skills'] if s['code'] == 'YY.S36')
        assert same['result']['job_id'] == job['id']
