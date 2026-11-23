import pytest

from process_planning.planning import render_route
from process_planning.store import Store


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "workspace")
    store.initialize()
    return store


def test_template_customization_history_and_restore(store):
    original = store.template_get()
    assert original["source"] == "builtin"
    custom = original["html"].replace("МАРШРУТНАЯ КАРТА", "МОЙ ЗАВОД · МАРШРУТНАЯ КАРТА")
    change = store.template_edit(original["revision"], custom, "Company branding")
    assert change["changed"]
    assert store.template_get()["source"] == "workspace"
    assert "МОЙ ЗАВОД" in store.template_get()["html"]
    assert store.template_get(original["revision"])["html"] == original["html"]
    assert store.history()["commits"][0]["label"] == "Company branding"
    store.template_edit(change["revision"], original["html"], "Restore original appearance")
    assert store.template_get()["html"].strip() == original["html"].strip()


@pytest.mark.parametrize("html", ["", "$rows $unknown", "<p>No operations</p>", "$rows $", "$rows " + "я" * 32_000])
def test_invalid_template_does_not_change_workspace(store, html):
    head = store.revision()
    with pytest.raises(ValueError):
        store.template_edit(head, html, "Invalid template")
    assert store.revision() == head
    assert store.template_get()["source"] == "builtin"
    assert not store.git("status", "--porcelain")


def test_template_conflict_and_generic_edit_rejected(store):
    initial = store.revision()
    store.template_edit(initial, "<table>$rows</table>", "Minimal template")
    with pytest.raises(ValueError, match="revision_conflict"):
        store.template_edit(initial, "<table>$rows</table>", "Stale template")
    with pytest.raises(ValueError, match="use template_edit"):
        store.apply(store.revision(), "Bypass template tool", [{"op": "delete", "path": "templates/route.html"}])
    assert store.template_get()["html"] == "<table>$rows</table>"


def test_route_uses_template_at_requested_revision(store):
    from test_store import plan, put, resource

    passport = put(store, "factory/equipment/a.json", resource())
    old_revision = put(store, "processes/plan.json", plan(passport))
    store.template_edit(old_revision, "<h1>Company: $name</h1><table>$rows</table><p>$$100</p>", "Custom layout")
    assert "Company:" in render_route(store, "processes/plan.json")["html"]
    assert "$100" in render_route(store, "processes/plan.json")["html"]
    old = render_route(store, "processes/plan.json", old_revision)
    assert "Company:" not in old["html"]
    assert old["template"]["source"] == "builtin"


def test_failed_record_edit_preserves_custom_template(store):
    store.template_edit(store.revision(), "<table>$rows</table>", "Custom template")
    head = store.revision()
    with pytest.raises(ValueError):
        store.apply(head, "Invalid card", [{"op": "put", "path": "factory/equipment/a.json", "record": {}}])
    assert store.template_get()["html"] == "<table>$rows</table>"
    assert not store.git("status", "--porcelain")
