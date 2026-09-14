from fastapi.testclient import TestClient

from app.main import app


def create_draft(client, skill_code="YY.S01"):
    response = client.post(
        "/api/v2/scoring-rubrics/drafts", json={"skill_code": skill_code}
    )
    assert response.status_code == 201
    return response.json()


def test_v2_current_and_skill_rubric_include_school_hierarchy_and_anchors():
    with TestClient(app) as client:
        current = client.get("/api/v2/rubrics/current")
        scoring = client.get("/api/v2/skills/YY.S01/scoring-rubric")
    assert current.status_code == 200
    assert (current.json()["goals"], current.json()["capabilities"], current.json()["skills"]) == (3, 10, 38)
    assert scoring.status_code == 200
    assert len(scoring.json()["groups"]) == 6
    assert all(indicator["anchors"] and len(indicator["anchors"]) == 5 for group in scoring.json()["groups"] for indicator in group["indicators"])


def test_draft_clones_the_published_config_and_rejects_extra_fields():
    with TestClient(app) as client:
        draft = create_draft(client)
        bad = client.post(
            "/api/v2/scoring-rubrics/drafts",
            json={"skill_code": "YY.S01", "weight": 9},
        )
        detail = client.get(f"/api/v2/scoring-rubrics/{draft['id']}")
    assert draft["status"] == "draft"
    assert draft["version"] == 2
    assert bad.status_code == 422
    assert len(detail.json()["groups"]) == 6
    assert sum(len(group["indicators"]) for group in detail.json()["groups"]) > 6


def test_draft_can_edit_indicators_and_move_to_reviewed():
    with TestClient(app) as client:
        draft = create_draft(client)
        detail = client.get(f"/api/v2/scoring-rubrics/{draft['id']}").json()
        indicator = detail["groups"][0]["indicators"][0]
        edited = client.patch(
            f"/api/v2/scoring-rubrics/{draft['id']}",
            json={
                "indicator_updates": [
                    {
                        "indicator_id": indicator["database_id"],
                        "source_text": "修订后的模拟指标",
                        "anchors": ["0", "1", "2", "3", "4"],
                    }
                ]
            },
        )
        reviewed = client.patch(
            f"/api/v2/scoring-rubrics/{draft['id']}", json={"status": "reviewed"}
        )
        rejected_edit = client.patch(
            f"/api/v2/scoring-rubrics/{draft['id']}",
            json={"indicator_updates": [{"indicator_id": indicator["database_id"], "weight": 1}]},
        )
    assert edited.status_code == 200
    assert reviewed.json()["status"] == "reviewed"
    assert rejected_edit.status_code == 409


def test_reviewed_config_publishes_and_archives_the_previous_version():
    with TestClient(app) as client:
        draft = create_draft(client)
        assert client.post(f"/api/v2/scoring-rubrics/{draft['id']}/publish").status_code == 409
        client.patch(f"/api/v2/scoring-rubrics/{draft['id']}", json={"status": "reviewed"})
        published = client.post(f"/api/v2/scoring-rubrics/{draft['id']}/publish")
        old = client.patch("/api/v2/scoring-rubrics/1", json={"status": "reviewed"})
        active = client.get("/api/v2/skills/YY.S01/scoring-rubric")
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert old.status_code == 409
    assert active.json()["version"] == 2


def test_reviewed_config_can_be_archived_without_publishing():
    with TestClient(app) as client:
        draft = create_draft(client, "YY.S02")
        client.patch(
            f"/api/v2/scoring-rubrics/{draft['id']}", json={"status": "reviewed"}
        )
        archived = client.patch(
            f"/api/v2/scoring-rubrics/{draft['id']}", json={"status": "archived"}
        )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_publish_rejects_invalid_group_weights():
    with TestClient(app) as client:
        draft = create_draft(client)
        detail = client.get(f"/api/v2/scoring-rubrics/{draft['id']}").json()
        group = detail["groups"][0]
        changed = client.patch(
            f"/api/v2/scoring-rubrics/{draft['id']}",
            json={"group_updates": [{"group_id": group["database_id"], "weight": 0.5}]},
        )
        client.patch(f"/api/v2/scoring-rubrics/{draft['id']}", json={"status": "reviewed"})
        published = client.post(f"/api/v2/scoring-rubrics/{draft['id']}/publish")
    assert changed.status_code == 200
    assert published.status_code == 422


def test_targets_are_versioned_and_filterable():
    with TestClient(app) as client:
        created = client.put(
            "/api/v2/targets/3-6/2026-1/YY.S01",
            json={"target_level": 4, "target_version": "yy-2026-1-v1"},
        )
        duplicate = client.put(
            "/api/v2/targets/3-6/2026-1/YY.S01",
            json={"target_level": 2, "target_version": "yy-2026-1-v1"},
        )
        invalid = client.put(
            "/api/v2/targets/3-6/2026-1/YY.S02",
            json={"target_level": 7, "target_version": "bad"},
        )
        targets = client.get(
            "/api/v2/targets", params={"grade": "3-6", "term": "2026-1", "skill_code": "YY.S01"}
        )
    assert created.status_code == 201
    assert created.json()["target_level"] == 4
    assert duplicate.status_code == 409
    assert invalid.status_code == 422
    assert len(targets.json()["items"]) == 1
    assert targets.json()["items"][0]["target_version"] == "yy-2026-1-v1"


def test_target_queries_and_current_catalog_ignore_other_rubrics():
    from app.database import v2_catalog

    with TestClient(app) as client:
        from test_rubric_v2 import insert_second_rubric

        insert_second_rubric()
        targets = client.get(
            "/api/v2/targets",
            params={"grade": "3-6", "term": "manual", "skill_code": "YY.S01"},
        )
        created = client.put(
            "/api/v2/targets/3-6/manual/YY.S01",
            json={"target_level": 3, "target_version": "current-manual-v1"},
        )
    assert targets.json()["items"] == []
    assert created.json()["target_version"] == "current-manual-v1"
    assert (v2_catalog()["goals"], v2_catalog()["capabilities"], v2_catalog()["skills"]) == (3, 10, 38)


def test_missing_configs_and_skills_return_404():
    with TestClient(app) as client:
        assert client.get("/api/v2/scoring-rubrics/999999").status_code == 404
        assert client.get("/api/v2/skills/YY.S99/scoring-rubric").status_code == 404
        assert client.post("/api/v2/scoring-rubrics/drafts", json={"skill_code": "YY.S99"}).status_code == 404
