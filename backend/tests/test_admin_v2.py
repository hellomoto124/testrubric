from fastapi.testclient import TestClient

from app.main import app


def test_scoring_config_list_exposes_versions_without_weights_for_teacher_ui():
    with TestClient(app) as client:
        response = client.get(
            "/api/v2/scoring-rubrics", params={"skill_code": "YY.S01"}
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["skill_code"] == "YY.S01"
    assert response.json()["items"][0]["status"] == "published"
    assert set(response.json()["items"][0]) >= {
        "id",
        "version",
        "status",
        "calibration_status",
        "group_count",
    }


def test_report_audit_returns_versioned_job_summary_without_evidence_content():
    with TestClient(app) as client:
        response = client.get("/api/v2/reports/audit", params={"limit": 10})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert set(item) >= {
        "job_id",
        "student_id",
        "skill_code",
        "status",
        "rubric_code",
        "scoring_config_version",
        "target_version",
        "engine",
    }
    assert "evidence_text" not in str(response.json())
    assert "judgments" not in str(response.json())


def test_system_status_masks_secret_and_reports_runtime_counts(monkeypatch):
    from app.admin_v2 import record_worker_heartbeat

    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "qwen-test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "secret-value")
    with TestClient(app) as client:
        record_worker_heartbeat()
        response = client.get("/api/v2/system/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == {
        "name": "qwen-test",
        "base_url": "https://example.invalid/v1",
        "api_key_configured": True,
        "vision_enabled": False,
        "demo_agent_mode": True,
    }
    assert "secret-value" not in str(payload)
    assert payload["worker"]["status"] == "online"
    assert payload["data_counts"]["students"] == 20
    assert payload["rubric"]["skills"] == 38


def test_demo_system_settings_are_persisted_and_reject_secret_fields():
    with TestClient(app) as client:
        updated = client.put(
            "/api/v2/system/settings",
            json={
                "academic_year": "2026-2027",
                "term": "第一学期",
                "default_grade": "三年级",
            },
        )
        rejected = client.put(
            "/api/v2/system/settings",
            json={"OPENAI_COMPATIBLE_API_KEY": "must-not-be-accepted"},
        )
        status = client.get("/api/v2/system/status")

    assert updated.status_code == 200
    assert status.json()["settings"] == {
        "academic_year": "2026-2027",
        "term": "第一学期",
        "default_grade": "三年级",
    }
    assert rejected.status_code == 422


def test_new_default_target_flows_to_dashboard_and_new_job_snapshot():
    with TestClient(app) as client:
        target = client.put(
            "/api/v2/targets/3-6/default/YY.S01",
            json={"target_level": 5, "target_version": "admin-default-v2"},
        )
        dashboard = client.get(
            "/api/v2/dashboard/school/1", params={"skill_code": "YY.S01"}
        )
        evidence = client.post(
            "/api/evidence",
            json={
                "student_id": 1,
                "evidence_type": "teacher_observation",
                "text": "模拟测试数据：用于目标快照验证。",
            },
        ).json()
        job = client.post(
            "/api/v2/assessment-jobs",
            json={
                "student_id": 1,
                "skill_code": "YY.S01",
                "evidence_refs": [evidence["id"]],
                "context": "目标版本测试",
                "support_level": "无",
                "period": "default",
                "idempotency_key": "admin-target-snapshot",
            },
        )

    assert target.status_code == 201
    skill = dashboard.json()["goals"][0]["capabilities"][0]["skills"][0]
    assert (skill["target_level"], skill["target_version"]) == (
        5,
        "admin-default-v2",
    )
    assert job.json()["target_snapshot"]["target_level"] == 5
    assert job.json()["target_snapshot"]["target_version"] == "admin-default-v2"
