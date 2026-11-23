from html import escape
from string import Template

from .models import ProcessPlan
from .store import Store


def assess(store: Store, path: str, revision: str | None = None) -> dict:
    with store.locked():
        rev = store.revision(revision)
        if not path.startswith("processes/"):
            raise ValueError("provide a process plan path")
        plan = ProcessPlan.model_validate(store.load(path, rev))
        passport = store.revision(plan.passport_revision)
        resources = {}
        for filename in store.files(passport):
            if filename.startswith("factory/") and filename.endswith(".json"):
                record = store.load(filename, passport)
                resources[record["id"]] = record
        findings = []
        if not plan.operations:
            findings.append({"status": "fail", "code": "empty_route"})
        for operation in plan.operations:
            for resource_id in operation.resource_ids:
                resource = resources.get(resource_id)
                if resource is None:
                    findings.append({"status": "fail", "code": "missing_resource", "operation": operation.id, "resource": resource_id})
                elif resource["availability"] != "available" or resource["evidence"]["status"] != "confirmed":
                    findings.append({"status": "unknown", "code": "resource_requires_confirmation", "operation": operation.id, "resource": resource_id, "availability": resource["availability"]})
            if not operation.resource_ids:
                findings.append({"status": "unknown", "code": "no_resources", "operation": operation.id})
            if operation.time_minutes is not None and not operation.time_source:
                findings.append({"status": "unknown", "code": "time_without_source", "operation": operation.id})
        if plan.open_questions:
            findings.append({"status": "unknown", "code": "open_questions", "count": len(plan.open_questions)})
        structural = "fail" if any(f["status"] == "fail" for f in findings) else "unknown" if findings else "pass"
        return {"revision": rev, "passport_revision": passport, "structural_status": structural,
                "engineering_status": "unknown", "findings": findings,
                "unchecked": ["machining feasibility", "accuracy and tolerances", "cutting conditions", "time standards", "ESTD compliance"],
                "plan": plan.model_dump()}


def render_route(store: Store, path: str, revision: str | None = None) -> dict:
    assessment = assess(store, path, revision)
    plan = ProcessPlan.model_validate(assessment.pop("plan"))
    e = lambda value: escape(str(value), quote=True)
    rows = []
    for op in plan.operations:
        rows.append("<tr class='operation'>" + "".join(f"<td>{e(v)}</td>" for v in (
            op.id, op.name, ", ".join(op.resource_ids),
            "\n".join(op.setups + op.transitions), "\n".join(op.control),
            "" if op.time_minutes is None else op.time_minutes)) + "</tr>")
    for _ in range(max(0, 7 - len(plan.operations))):
        rows.append("<tr class='blank'>" + "<td>&nbsp;</td>" * 6 + "</tr>")
    template_info = store.template_get(assessment["revision"])
    template = Template(template_info["html"])
    html = template.substitute(name=e(plan.name), designation=e(plan.id), material=e(plan.material),
                               blank=e(plan.blank), rows="".join(rows), revision=e(assessment["revision"]),
                               passport_revision=e(plan.passport_revision))
    return {"media_type": "text/html", "html": html, "validation": assessment,
            "template": {k: template_info[k] for k in ("source", "path", "revision")}}
