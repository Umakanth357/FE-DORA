"""
Ingestion Pipeline
Detects payload type → validates per-record → transforms → inserts → triggers metrics.
"""
import json, time
from datetime import datetime, timezone
from pydantic import ValidationError
from app.models.payloads import (CommitRecord, PRRecord, PipelineRunRecord,
                                  IncidentRecord, SCMPayload, CICDPayload, ITSMPayload)
from app.transformers import scm as scm_tx, cicd as cicd_tx
from app.transformers.itsm import process_incidents
from app.db import inserters
from app.db.registry import register_project, get_project
from app.core.config import get_settings
from app.core.logging import logger


def detect_type(raw: dict) -> str:
    if "commits" in raw or "pull_requests" in raw:
        return "scm"
    if "pipeline_runs" in raw:
        return "cicd"
    if "incidents" in raw:
        return "itsm"
    raise ValueError(
        "Cannot detect data type. JSON must contain: "
        "commits/pull_requests, pipeline_runs, or incidents"
    )


def _safe_validate(records: list, model_cls, label: str) -> tuple[list, list]:
    valid, errors = [], []
    for i, raw in enumerate(records):
        try:
            valid.append(model_cls(**raw))
        except Exception as e:
            nat_id = (raw.get("sha") or raw.get("pr_id") or
                      raw.get("pipeline_run_id") or raw.get("issue_id") or f"row_{i}")
            errors.append({"row": i, "type": label, "id": str(nat_id), "reason": str(e)})
    return valid, errors


def _run_scm(raw: dict, project_id: str) -> dict:
    errors = []
    inserted = {"commits": 0, "pull_requests": 0}

    valid_commits, errs = _safe_validate(raw.get("commits", []), CommitRecord, "commit")
    errors.extend(errs)

    valid_prs, errs = _safe_validate(raw.get("pull_requests", []), PRRecord, "pull_request")
    errors.extend(errs)

    # Build commit map for Lead Time denormalisation
    commit_map = {c.sha: c.committed_at for c in valid_commits}

    if valid_commits:
        rows = scm_tx.transform_commits(valid_commits, project_id)
        inserted["commits"] = inserters.insert_commits(rows)

    if valid_prs:
        rows = scm_tx.transform_pull_requests(valid_prs, project_id, commit_map)
        inserted["pull_requests"] = inserters.insert_pull_requests(rows)

    return {"inserted": inserted, "errors": errors, "deployment_rows": []}


def _run_cicd(raw: dict, project_id: str) -> dict:
    errors = []
    inserted = {"deployments": 0}

    valid_runs, errs = _safe_validate(
        raw.get("pipeline_runs", []), PipelineRunRecord, "pipeline_run")
    errors.extend(errs)

    deployment_rows = []
    if valid_runs:
        rows = cicd_tx.transform_deployments(valid_runs, project_id)
        inserted["deployments"] = inserters.insert_deployments(rows)
        deployment_rows = rows

    return {"inserted": inserted, "errors": errors, "deployment_rows": deployment_rows}


def _run_itsm(raw: dict, project_id: str) -> dict:
    s = get_settings()
    errors = []
    inserted = {"incidents": 0}

    valid_incs, errs = _safe_validate(
        raw.get("incidents", []), IncidentRecord, "incident")
    errors.extend(errs)

    # Fetch recent deployments for time-window linking
    from app.db.connection import get_engine
    from sqlalchemy import text
    engine = get_engine()
    with engine.connect() as conn:
        dep_rows = conn.execute(text("""
            SELECT id, external_id, finished_at, result, environment
            FROM deployments
            WHERE project_id = :pid
              AND environment = 'PRODUCTION'
              AND finished_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            ORDER BY finished_at DESC
        """), {"pid": project_id}).fetchall()
    deployments = [dict(r._mapping) for r in dep_rows]

    classification_summary = {}
    if valid_incs:
        rows, classification_summary = process_incidents(
            records=valid_incs,
            project_id=project_id,
            deployments=deployments,
            window_hours=s.incident_link_window_hrs,
            threshold=40,
        )
        inserted["incidents"] = inserters.insert_incidents(rows)

    return {
        "inserted": inserted,
        "errors":   errors,
        "deployment_rows": [],
        "classification_summary": classification_summary,
    }


def ingest(raw: dict) -> dict:
    """
    Main entry point. Auto-detects type, registers project,
    runs pipeline, triggers metric recompute, returns response.
    """
    t0 = time.time()

    if "meta" not in raw:
        raise ValueError("JSON must contain a 'meta' block")

    project_id  = raw["meta"].get("project_name", "").strip()
    source_tool = raw["meta"].get("source_tool", "")
    if not project_id:
        raise ValueError("meta.project_name is required")

    # Register project (idempotent)
    register_project(project_id)

    data_type = detect_type(raw)
    logger.info(f"Ingesting {data_type} / {source_tool} for project: {project_id}")

    if data_type == "scm":
        result = _run_scm(raw, project_id)
    elif data_type == "cicd":
        result = _run_cicd(raw, project_id)
    elif data_type == "itsm":
        result = _run_itsm(raw, project_id)
    else:
        raise ValueError(f"Unknown data type: {data_type}")

    duration_ms = int((time.time() - t0) * 1000)
    total_inserted = sum(result["inserted"].values())

    # Audit log
    inserters.log_ingestion(
        project_id=project_id,
        file_type=data_type,
        source_tool=source_tool,
        inserted=total_inserted,
        updated=0,
        skipped=len(result["errors"]),
        errors=result["errors"],
        duration_ms=duration_ms,
    )

    # Trigger metric recompute in background
    try:
        from app.core.metrics import materialise_dora_daily
        from datetime import date
        materialise_dora_daily(project_id, date.today())
        logger.info(f"DORA metrics recomputed for {project_id}")
    except Exception as e:
        logger.warning(f"Metric recompute failed (non-fatal): {e}")

    return {
        "status":      "ok",
        "project_id":  project_id,
        "data_type":   data_type,
        "source_tool": source_tool,
        "inserted":    result["inserted"],
        "skipped":     len(result["errors"]),
        "errors":      result["errors"][:20],
        "duration_ms": duration_ms,
        "classification_summary": result.get("classification_summary", {}),
    }
