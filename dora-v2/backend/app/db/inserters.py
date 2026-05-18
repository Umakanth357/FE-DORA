"""
Bulk inserters for all DORA platform tables.
All operations are idempotent — safe to re-upload same data.
Batch size 500 rows per execute to avoid MySQL max_packet issues.
"""
import json
from datetime import datetime, timezone
from sqlalchemy import text
from app.db.connection import get_engine
from app.core.logging import logger

BATCH = 500


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:23]


# ── Commits ───────────────────────────────────────────────────────────────────

def insert_commits(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = text("""
        INSERT INTO commits
            (project_id, sha, author_name, author_email,
             committed_at, message, additions, deletions, branch)
        VALUES
            (:project_id, :sha, :author_name, :author_email,
             :committed_at, :message, :additions, :deletions, :branch)
        ON DUPLICATE KEY UPDATE
            author_name  = VALUES(author_name),
            message      = VALUES(message),
            additions    = VALUES(additions),
            deletions    = VALUES(deletions)
    """)
    n = 0
    with get_engine().begin() as conn:
        for batch in _chunks(rows, BATCH):
            conn.execute(sql, batch)
            n += len(batch)
    logger.info(f"Upserted {n} commits")
    return n


# ── Pull Requests ─────────────────────────────────────────────────────────────

def insert_pull_requests(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = text("""
        INSERT INTO pull_requests
            (project_id, external_id, title, status, author,
             base_branch, head_branch, created_at, merged_at, closed_at,
             first_commit_sha, first_commit_at)
        VALUES
            (:project_id, :external_id, :title, :status, :author,
             :base_branch, :head_branch, :created_at, :merged_at, :closed_at,
             :first_commit_sha, :first_commit_at)
        ON DUPLICATE KEY UPDATE
            status           = VALUES(status),
            merged_at        = VALUES(merged_at),
            closed_at        = VALUES(closed_at),
            first_commit_sha = VALUES(first_commit_sha),
            first_commit_at  = VALUES(first_commit_at)
    """)
    n = 0
    with get_engine().begin() as conn:
        for batch in _chunks(rows, BATCH):
            conn.execute(sql, batch)
            n += len(batch)
    logger.info(f"Upserted {n} pull_requests")
    return n


# ── Deployments ───────────────────────────────────────────────────────────────

def insert_deployments(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = text("""
        INSERT INTO deployments
            (project_id, external_id, pipeline_name, environment,
             result, started_at, finished_at, commit_sha,
             triggered_by, duration_secs)
        VALUES
            (:project_id, :external_id, :pipeline_name, :environment,
             :result, :started_at, :finished_at, :commit_sha,
             :triggered_by, :duration_secs)
        ON DUPLICATE KEY UPDATE
            result        = VALUES(result),
            finished_at   = VALUES(finished_at),
            duration_secs = VALUES(duration_secs)
    """)
    n = 0
    with get_engine().begin() as conn:
        for batch in _chunks(rows, BATCH):
            conn.execute(sql, batch)
            n += len(batch)
    logger.info(f"Upserted {n} deployments")
    return n


# ── Incidents ─────────────────────────────────────────────────────────────────

def insert_incidents(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = text("""
        INSERT INTO incidents
            (project_id, external_id, title, severity, status,
             classification, classification_confidence,
             dora_relevant, cfr_include, needs_review,
             created_at, resolved_at, mttr_minutes,
             linked_deployment_id, link_method,
             raw_category, raw_labels, change_request_id,
             service_affected, assignee)
        VALUES
            (:project_id, :external_id, :title, :severity, :status,
             :classification, :classification_confidence,
             :dora_relevant, :cfr_include, :needs_review,
             :created_at, :resolved_at, :mttr_minutes,
             :linked_deployment_id, :link_method,
             :raw_category, :raw_labels, :change_request_id,
             :service_affected, :assignee)
        ON DUPLICATE KEY UPDATE
            status                    = VALUES(status),
            resolved_at               = VALUES(resolved_at),
            mttr_minutes              = VALUES(mttr_minutes),
            classification            = VALUES(classification),
            classification_confidence = VALUES(classification_confidence),
            dora_relevant             = VALUES(dora_relevant),
            cfr_include               = VALUES(cfr_include),
            needs_review              = VALUES(needs_review),
            linked_deployment_id      = VALUES(linked_deployment_id),
            link_method               = VALUES(link_method)
    """)
    n = 0
    with get_engine().begin() as conn:
        for batch in _chunks(rows, BATCH):
            conn.execute(sql, batch)
            n += len(batch)
    logger.info(f"Upserted {n} incidents")
    return n


# ── Ingestion audit log ───────────────────────────────────────────────────────

def log_ingestion(project_id: str, file_type: str, source_tool: str,
                  inserted: int, updated: int, skipped: int,
                  errors: list, duration_ms: int):
    sql = text("""
        INSERT INTO ingestion_runs
            (project_id, file_type, source_tool, records_inserted,
             records_updated, records_skipped, errors_json, duration_ms, created_at)
        VALUES
            (:pid, :ftype, :tool, :ins, :upd, :skip, :errs, :dur, :now)
    """)
    with get_engine().begin() as conn:
        conn.execute(sql, {
            "pid":   project_id,
            "ftype": file_type,
            "tool":  source_tool,
            "ins":   inserted,
            "upd":   updated,
            "skip":  skipped,
            "errs":  json.dumps(errors[:50]),
            "dur":   duration_ms,
            "now":   _now(),
        })
