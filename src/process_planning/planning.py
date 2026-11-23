from html import escape

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
        rows.append("<tr>" + "".join(f"<td>{e(v)}</td>" for v in (
            op.id, op.name, ", ".join(op.resource_ids), "\n".join(op.setups),
            "\n".join(op.transitions), "\n".join(op.control),
            "—" if op.time_minutes is None else f"{op.time_minutes} ({op.time_source or 'источник не указан'})")) + "</tr>")
    html = "<!doctype html><html lang='ru'><meta charset='utf-8'><title>Маршрутная карта — черновик</title>"
    html += "<style>body{font:14px sans-serif;margin:28px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #aaa;padding:7px;white-space:pre-wrap}small{overflow-wrap:anywhere}</style>"
    html += f"<h1>{e(plan.name)}</h1><p>ЧЕРНОВИК. Обзорная форма; соответствие ЕСТД не проверено.</p>"
    html += f"<p>Деталь: {e(plan.part_revision)}. Источник КД: {e(plan.drawing_source)}</p>"
    html += f"<p>Материал: {e(plan.material)}. Заготовка: {e(plan.blank)}</p>"
    html += f"<small>Ревизия техпроцесса: {e(assessment['revision'])}<br>Паспорт: {e(plan.passport_revision)}</small>"
    html += "<table><thead><tr><th>№</th><th>Операция</th><th>Ресурсы</th><th>Установы</th><th>Переходы</th><th>Контроль</th><th>Время, мин</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    for title, items in (("Допущения", plan.assumptions), ("Нерешённые вопросы", plan.open_questions)):
        html += f"<h2>{title}</h2><ul>" + "".join(f"<li>{e(item)}</li>" for item in items) + "</ul>"
    html += f"<p>Структура: {e(assessment['structural_status'])}. Инженерная проверка: не выполнена.</p>"
    html += "<ul>" + "".join(f"<li>{e(item)}</li>" for item in assessment["findings"]) + "</ul></html>"
    return {"media_type": "text/html", "html": html, "validation": assessment}
