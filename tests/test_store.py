import json

import pytest

from process_planning.planning import assess, render_route
from process_planning.store import Store


def resource(id="TEST-001"):
    return {"id": id, "name": "<Станок>", "kind": "equipment", "availability": "available", "evidence": {"source": "test fixture, not real factory data", "observed_at": "2026-11-24", "status": "confirmed"}}


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "workspace")
    s.initialize()
    return s


def put(store, path, record):
    return store.apply(store.history()["commits"][0]["revision"], "test edit", [{"op": "put", "path": path, "record": record}])["revision"]


def plan(revision):
    return {"id": "PLAN-001", "name": "Test route", "part_revision": "A", "drawing_source": "test fixture", "passport_revision": revision,
            "material": "test material", "blank": "test blank", "assumptions": ["<script>alert(1)</script>"],
            "operations": [{"id": "010", "name": "Test operation", "resource_ids": ["TEST-001"], "transitions": ["Test transition"]}]}


def test_directory_move_and_pinned_passport(store):
    rev = put(store, "factory/equipment/turning/станок.json", resource())
    put(store, "processes/plan.json", plan(rev))
    assert assess(store, "processes/plan.json")["structural_status"] == "pass"
    head = store.revision()
    store.apply(head, "Move section", [{"op": "move", "path": "factory/equipment/turning", "destination": "factory/equipment/lathes"}])
    assert store.read("factory/equipment/lathes/станок.json")["record"]["id"] == "TEST-001"
    assert store.read("factory/equipment/turning/станок.json", rev)["record"]["id"] == "TEST-001"
    unavailable = resource()
    unavailable["availability"] = "unavailable"
    put(store, "factory/equipment/lathes/станок.json", unavailable)
    assert assess(store, "processes/plan.json")["structural_status"] == "pass"
    assert store.impact("TEST-001")["processes"][0]["id"] == "PLAN-001"
    assert store.browse("factory/equipment")["entries"][0]["type"] == "directory"


def test_atomic_rollback_duplicate_and_conflict(store):
    head = put(store, "factory/equipment/a.json", resource())
    with pytest.raises(ValueError, match="duplicate_id"):
        store.apply(head, "Invalid batch", [{"op": "put", "path": "factory/equipment/b.json", "record": resource()}])
    assert store.revision() == head
    assert not store.path("factory/equipment/b.json").exists()
    assert not store.git("status", "--porcelain")
    with pytest.raises(ValueError, match="revision_conflict"):
        store.apply("0" * 40, "Stale edit", [{"op": "delete", "path": "factory/equipment/a.json"}])
    assert store.read("factory/equipment/a.json")["record"]["id"] == "TEST-001"


@pytest.mark.parametrize("path", ["../outside", "factory/../outside", "factory/a/../../outside", "C:/tmp", "factory\\a", "factory/.git/config", "/factory/x", "factory//x", "factory/a\nb.json"])
def test_path_guard(store, path):
    with pytest.raises(ValueError):
        store.path(path)


def test_failure_does_not_leave_partial_batch(store):
    head = store.revision()
    with pytest.raises(ValueError):
        store.apply(head, "Partial failure", [{"op": "mkdir", "path": "factory/custom"}, {"op": "put", "path": "factory/custom/a.json", "record": {"invalid": True}}])
    assert store.revision() == head
    assert not store.path("factory/custom").exists()
    assert not store.git("status", "--porcelain")


def test_missing_and_unconfirmed_resources(store):
    r = resource()
    r["evidence"]["status"] = "assumed"
    rev = put(store, "factory/equipment/a.json", r)
    put(store, "processes/plan.json", plan(rev))
    result = assess(store, "processes/plan.json")
    assert result["structural_status"] == "unknown"
    assert result["engineering_status"] == "unknown"
    missing = plan(store.history()["commits"][-1]["revision"])
    put(store, "processes/plan.json", missing)
    assert assess(store, "processes/plan.json")["structural_status"] == "fail"


def test_render_escapes_and_carries_revision(store):
    rev = put(store, "factory/equipment/a.json", resource())
    record = plan(rev)
    record["operations"][0]["name"] = "<script>operation</script>"
    record["open_questions"] = ["Private review question"]
    put(store, "processes/plan.json", record)
    result = render_route(store, "processes/plan.json")
    assert "<script>" not in result["html"]
    assert "&lt;script&gt;" in result["html"]
    assert rev in result["html"]
    assert "МАРШРУТНАЯ КАРТА" in result["html"]
    assert "Допущения" not in result["html"]
    assert "Private review question" not in result["html"]
    assert "missing_resource" not in result["html"]
    assert result["validation"]["findings"]


def test_external_edits_rejected(store):
    store.path("factory/manual.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="workspace_dirty"):
        store.apply(store.revision(), "Edit", [{"op": "mkdir", "path": "factory/custom"}])
    assert json.loads(store.path("factory/manual.json").read_text()) == {}


def test_pagination_and_stable_id(store):
    for i in range(3):
        put(store, f"factory/equipment/{i}.json", resource(f"TEST-{i}"))
    page = store.browse("factory", limit=2, text="Станок")
    assert page["truncated"] and page["matched"] == 3
    assert len(store.browse("factory", offset=page["next_offset"], limit=2, text="Станок")["entries"]) == 1
    with pytest.raises(ValueError, match="stable_id"):
        put(store, "factory/equipment/0.json", resource("RENAMED"))
