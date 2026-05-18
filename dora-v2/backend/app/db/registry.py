from datetime import datetime, timezone
from sqlalchemy import text
from app.db.connection import get_engine
from app.core.logging import logger


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:23]


def register_project(project_id: str, display_name: str = None, team: str = None) -> dict:
    """Create project if not exists. Idempotent."""
    engine = get_engine()
    now    = _now()
    dname  = display_name or project_id.replace("-", " ").replace("_", " ").title()

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO projects (id, display_name, team, created_at, updated_at)
            VALUES (:id, :dname, :team, :now, :now)
            ON DUPLICATE KEY UPDATE
                display_name = COALESCE(:dname, display_name),
                team         = COALESCE(:team, team),
                updated_at   = :now
        """), {"id": project_id, "dname": dname, "team": team, "now": now})

    logger.info(f"Project registered: {project_id}")
    return get_project(project_id)


def get_project(project_id: str) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, display_name, team, created_at, updated_at FROM projects WHERE id = :id"),
            {"id": project_id}
        ).fetchone()
        if not row:
            return None

        counts = conn.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM commits     WHERE project_id = :pid) AS commits,
                (SELECT COUNT(*) FROM pull_requests WHERE project_id = :pid) AS pull_requests,
                (SELECT COUNT(*) FROM deployments WHERE project_id = :pid) AS deployments,
                (SELECT COUNT(*) FROM incidents   WHERE project_id = :pid) AS incidents,
                (SELECT COUNT(*) FROM incidents   WHERE project_id = :pid AND needs_review = 1) AS needs_review
        """), {"pid": project_id}).fetchone()

        last = conn.execute(text("""
            SELECT created_at FROM ingestion_runs
            WHERE project_id = :pid ORDER BY created_at DESC LIMIT 1
        """), {"pid": project_id}).fetchone()

        latest_dora = conn.execute(text("""
            SELECT overall_band, df_band, lt_band, cfr_band, mttr_band, metric_date
            FROM dora_daily WHERE project_id = :pid
            ORDER BY metric_date DESC LIMIT 1
        """), {"pid": project_id}).fetchone()

    return {
        "id":           row.id,
        "display_name": row.display_name,
        "team":         row.team,
        "created_at":   str(row.created_at),
        "record_counts": {
            "commits":       counts.commits       if counts else 0,
            "pull_requests": counts.pull_requests if counts else 0,
            "deployments":   counts.deployments   if counts else 0,
            "incidents":     counts.incidents     if counts else 0,
            "needs_review":  counts.needs_review  if counts else 0,
        },
        "last_ingestion": str(last.created_at) if last else None,
        "latest_dora": {
            "overall":  latest_dora.overall_band if latest_dora else None,
            "df":       latest_dora.df_band      if latest_dora else None,
            "lt":       latest_dora.lt_band      if latest_dora else None,
            "cfr":      latest_dora.cfr_band     if latest_dora else None,
            "mttr":     latest_dora.mttr_band    if latest_dora else None,
            "as_of":    str(latest_dora.metric_date) if latest_dora else None,
        } if latest_dora else None,
    }


def list_projects() -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id FROM projects ORDER BY created_at DESC")
        ).fetchall()
    result = []
    for r in rows:
        p = get_project(r.id)
        if p:
            result.append(p)
    return result
