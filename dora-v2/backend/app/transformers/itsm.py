from datetime import datetime, timedelta, timezone
from app.models.payloads import IncidentRecord
from app.transformers.utils import to_utc_mysql, calc_mttr_minutes, trunc
from app.core.classifier import classify_batch

STATUS_MAP = {"RESOLVED":"RESOLVED","OPEN":"OPEN","IN_PROGRESS":"IN_PROGRESS"}


def _parse_dt(ts: str) -> datetime:
    s = (ts or "").strip().replace(" ", "T")
    if s.endswith("Z"): s = s[:-1] + "+00:00"
    if "+" not in s[10:] and s.count("-") < 3: s += "+00:00"
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def link_to_deployments(incidents: list[dict], deployments: list[dict],
                         window_hours: int = 24) -> list[dict]:
    """
    Link incidents to deployments by explicit ID first,
    then time-window heuristic for DEPLOYMENT_FAILURE class only.
    """
    dep_by_ext = {d["external_id"]: d for d in deployments}

    for inc in incidents:
        # Explicit link
        if inc.get("related_deployment_id") and \
           inc["related_deployment_id"] in dep_by_ext:
            inc["_link_method"] = "explicit"
            inc["_dep_row"] = dep_by_ext[inc["related_deployment_id"]]
            continue

        # Skip non-deployment-failure incidents
        if not inc.get("_dora_relevant"):
            inc["_link_method"] = "skipped_not_dora"
            inc["_dep_row"] = None
            continue

        # Time-window
        try:
            inc_time = _parse_dt(inc["created_at"])
            win_start = inc_time - timedelta(hours=window_hours)
            candidate = None
            for dep in sorted(deployments,
                               key=lambda d: d.get("finished_at") or "", reverse=True):
                if not dep.get("finished_at"):
                    continue
                dep_time = _parse_dt(dep["finished_at"])
                if win_start <= dep_time <= inc_time:
                    candidate = dep
                    break
            if candidate:
                inc["related_deployment_id"] = candidate["external_id"]
                inc["_link_method"] = "time_window"
                inc["_dep_row"] = candidate
            else:
                inc["_link_method"] = "unlinked"
                inc["_dep_row"] = None
        except Exception:
            inc["_link_method"] = "error"
            inc["_dep_row"] = None

    return incidents


def process_incidents(records: list[IncidentRecord], project_id: str,
                       deployments: list[dict], window_hours: int = 24,
                       threshold: int = 40) -> tuple[list[dict], dict]:
    """Full pipeline: classify → link → transform → return (rows, summary)."""
    raw = [{
        "issue_id":              r.issue_id,
        "title":                 r.title or "",
        "description":           getattr(r, "description", "") or "",
        "category":              getattr(r, "category", "") or "",
        "labels":                getattr(r, "labels", []) or [],
        "status":                r.status,
        "severity":              r.severity,
        "created_at":            r.created_at,
        "resolved_at":           r.resolved_at,
        "related_deployment_id": r.related_deployment_id,
        "change_request_id":     getattr(r, "change_request_id", None),
        "service_affected":      getattr(r, "service_affected", None),
        "assignee":              r.assignee,
    } for r in records]

    classified = classify_batch(raw, threshold=threshold)
    linked     = link_to_deployments(classified, deployments, window_hours)
    rows       = _to_rows(linked, project_id)

    from collections import Counter
    by_type   = dict(Counter(i["_classification"] for i in linked))
    dora_cnt  = sum(1 for i in linked if i["_dora_relevant"])
    cfr_cnt   = sum(1 for i in linked if i["_cfr_include"])
    review_cnt = sum(1 for i in linked if i["_needs_review"])
    summary   = {
        "total":          len(linked),
        "by_type":        by_type,
        "dora_relevant":  dora_cnt,
        "cfr_eligible":   cfr_cnt,
        "needs_review":   review_cnt,
        "excluded":       len(linked) - dora_cnt,
    }
    return rows, summary


def _to_rows(incidents: list[dict], project_id: str) -> list[dict]:
    import json
    rows = []
    for inc in incidents:
        dep_row = inc.get("_dep_row")
        rows.append({
            "project_id":                 project_id,
            "external_id":               inc["issue_id"],
            "title":                     trunc(inc.get("title") or "", 500),
            "severity":                  inc.get("severity") or "P2",
            "status":                    STATUS_MAP.get(inc.get("status","OPEN"), "OPEN"),
            "classification":            inc["_classification"],
            "classification_confidence": inc["_confidence"],
            "dora_relevant":             1 if inc["_dora_relevant"] else 0,
            "cfr_include":               1 if inc["_cfr_include"]   else 0,
            "needs_review":              1 if inc["_needs_review"]   else 0,
            "created_at":                to_utc_mysql(inc["created_at"]),
            "resolved_at":               to_utc_mysql(inc.get("resolved_at")),
            "mttr_minutes":              calc_mttr_minutes(inc["created_at"], inc.get("resolved_at")),
            "linked_deployment_id":      dep_row["id"] if dep_row and dep_row.get("id") else None,
            "link_method":               inc.get("_link_method", "unlinked"),
            "raw_category":              trunc(inc.get("category") or ""),
            "raw_labels":                json.dumps(inc.get("labels") or []),
            "change_request_id":         trunc(inc.get("change_request_id") or ""),
            "service_affected":          trunc(inc.get("service_affected") or ""),
            "assignee":                  trunc(inc.get("assignee") or ""),
        })
    return rows
