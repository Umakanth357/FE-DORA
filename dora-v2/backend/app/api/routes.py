import json
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Body
from fastapi.responses import PlainTextResponse, JSONResponse
from app.core.pipeline import ingest
from app.core.metrics import compute_project_dora, materialise_dora_daily, materialise_all_projects
from app.db.registry import get_project, register_project, list_projects
from app.db.connection import check_db, get_engine
from app.core.config import get_settings
from app.core.logging import logger
from sqlalchemy import text
from datetime import date

router   = APIRouter()
settings = get_settings()


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok" if check_db() else "degraded",
            "db": "connected" if check_db() else "unreachable"}


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("/projects")
async def get_projects():
    return {"projects": list_projects()}


@router.get("/projects/{project_id}")
async def get_project_route(project_id: str):
    info = get_project(project_id)
    if not info:
        return JSONResponse(status_code=404, content={"exists": False, "project_id": project_id})
    return {"exists": True, **info}


@router.post("/projects")
async def create_project(body: dict = Body(...)):
    pid  = body.get("project_id", "").strip().lower()
    name = body.get("display_name", "")
    team = body.get("team", "")
    if not pid:
        raise HTTPException(400, "project_id is required")
    info = register_project(pid, name or None, team or None)
    return {"status": "ok", **info}


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb}MB limit")
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")
    if not isinstance(raw, dict):
        raise HTTPException(400, "JSON root must be an object")
    try:
        return ingest(raw)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.error(f"Ingestion error: {e}", exc_info=True)
        raise HTTPException(500, f"Ingestion failed: {e}")


# ── DORA Metrics ──────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/dora")
async def get_dora(
    project_id: str,
    window_days: int = Query(90, ge=7, le=365),
):
    """Full DORA computation for a project over the given window."""
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(404, f"Project not found: {project_id}")
    try:
        result = compute_project_dora(
            project_id=project_id,
            window_days=window_days,
            link_window_hours=settings.incident_link_window_hrs,
        )
        return {**result, "project": proj}
    except Exception as e:
        logger.error(f"Metric compute error: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@router.get("/projects/{project_id}/trends")
async def get_trends(
    project_id: str,
    days: int = Query(90, ge=7, le=365),
):
    """90-day daily trend data from dora_daily table."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                metric_date,
                deployments_total, deployments_success, deployments_failed,
                df_band,
                lead_time_p50_hrs, lead_time_p75_hrs, lead_time_p95_hrs,
                lead_time_sample_size, lt_band,
                cfr_deployments, cfr_incidents, change_failure_rate, cfr_band,
                mttr_p50_hrs, mttr_p75_hrs, mttr_p95_hrs, mttr_sample_size, mttr_band,
                overall_band, computed_at
            FROM dora_daily
            WHERE project_id = :pid
              AND metric_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
            ORDER BY metric_date ASC
        """), {"pid": project_id, "days": days}).fetchall()

    trend = [dict(r._mapping) for r in rows]
    # Convert Decimal/date types to JSON-safe
    for row in trend:
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
            elif hasattr(v, "__float__"):
                row[k] = float(v) if v is not None else None

    return {"project_id": project_id, "days": days, "trend": trend}


@router.post("/projects/{project_id}/recompute")
async def recompute_metrics(project_id: str):
    """Force-recompute dora_daily for a project (last 90 days)."""
    from app.core.metrics import materialise_dora_daily
    from datetime import timedelta
    today = date.today()
    written = 0
    for delta in range(90):
        d = today - timedelta(days=delta)
        try:
            materialise_dora_daily(project_id, d)
            written += 1
        except Exception as e:
            logger.warning(f"Failed {project_id}/{d}: {e}")
    return {"status": "ok", "days_written": written}


# ── Incidents ─────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/incidents")
async def get_incidents(
    project_id: str,
    classification: str  = Query(None),
    needs_review:   bool = Query(None),
    limit:          int  = Query(100, ge=1, le=500),
    offset:         int  = Query(0, ge=0),
):
    engine = get_engine()
    filters = ["project_id = :pid"]
    params  = {"pid": project_id, "limit": limit, "offset": offset}

    if classification:
        filters.append("classification = :cls")
        params["cls"] = classification.upper()
    if needs_review is not None:
        filters.append("needs_review = :nr")
        params["nr"] = 1 if needs_review else 0

    where = " AND ".join(filters)
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, external_id, title, severity, status,
                   classification, classification_confidence,
                   dora_relevant, cfr_include, needs_review,
                   created_at, resolved_at, mttr_minutes,
                   link_method, raw_category, assignee
            FROM incidents
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), params).fetchall()

        total = conn.execute(text(
            f"SELECT COUNT(*) FROM incidents WHERE {where}"),
            {k: v for k, v in params.items() if k not in ("limit","offset")}
        ).scalar()

    incidents = []
    for r in rows:
        row = dict(r._mapping)
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
        incidents.append(row)

    return {"project_id": project_id, "total": total,
            "limit": limit, "offset": offset, "incidents": incidents}


@router.post("/incidents/{incident_id}/reclassify")
async def reclassify_incident(
    incident_id: int,
    body: dict = Body(...),
):
    """Human override of incident classification."""
    new_class  = body.get("classification", "").upper()
    reviewer   = body.get("reviewer", "")
    notes      = body.get("notes", "")
    valid      = {"DEPLOYMENT_FAILURE","INFRASTRUCTURE","EXTERNAL_DEPENDENCY","SECURITY","OTHER"}
    if new_class not in valid:
        raise HTTPException(400, f"classification must be one of {valid}")

    dora_relevant = new_class == "DEPLOYMENT_FAILURE"
    engine = get_engine()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, project_id, classification FROM incidents WHERE id = :id"),
            {"id": incident_id}
        ).fetchone()
        if not row:
            raise HTTPException(404, "Incident not found")

        conn.execute(text("""
            UPDATE incidents
            SET classification = :cls,
                classification_confidence = 100,
                dora_relevant = :dora,
                cfr_include   = :cfr,
                needs_review  = 0,
                reviewed_by   = :reviewer,
                reviewed_at   = :now
            WHERE id = :id
        """), {
            "cls": new_class, "dora": int(dora_relevant),
            "cfr": int(dora_relevant), "reviewer": reviewer,
            "now": now, "id": incident_id,
        })

        conn.execute(text("""
            INSERT INTO incident_reviews
                (incident_id, project_id, original_class, new_class, reviewer, notes, reviewed_at)
            VALUES (:inc_id, :pid, :orig, :new, :reviewer, :notes, :now)
        """), {
            "inc_id": incident_id, "pid": row.project_id,
            "orig": row.classification, "new": new_class,
            "reviewer": reviewer, "notes": notes, "now": now,
        })

    return {"status": "ok", "incident_id": incident_id,
            "new_classification": new_class, "dora_relevant": dora_relevant}


# ── Script Download ───────────────────────────────────────────────────────────

SCRIPTS = {
    "github":         "scripts/collectors/collect_github.py",
    "gitlab":         "scripts/collectors/collect_gitlab.py",
    "bitbucket":      "scripts/collectors/collect_bitbucket.py",
    "jenkins":        "scripts/collectors/collect_jenkins.py",
    "github_actions": "scripts/collectors/collect_gha.py",
    "gitlab_ci":      "scripts/collectors/collect_gitlab_ci.py",
    "servicenow":     "scripts/collectors/collect_servicenow.py",
    "jira":           "scripts/collectors/collect_jira.py",
    "pagerduty":      "scripts/collectors/collect_pagerduty.py",
}


@router.get("/scripts/{tool}")
async def download_script(
    tool:    str,
    project: str = Query(...),
    days:    int = Query(180, ge=30, le=365),
):
    if tool not in SCRIPTS:
        raise HTTPException(404, f"No script for: {tool}. Available: {list(SCRIPTS)}")
    try:
        with open(SCRIPTS[tool]) as f:
            content = f.read()
    except FileNotFoundError:
        raise HTTPException(404, f"Script file missing on server: {SCRIPTS[tool]}")

    content = content.replace("__PROJECT_NAME__", project).replace("__DAYS__", str(days))
    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="collect_{tool}.py"'},
    )
