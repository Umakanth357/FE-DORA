"""
DORA Metric Engine
==================
Calculates all 4 DORA metrics from raw data tables
and materialises results into dora_daily.

Metric definitions follow the DORA State of DevOps Report 2023:
  - Deployment Frequency  : how often code ships to production
  - Lead Time for Changes : first commit → production
  - Change Failure Rate   : % of deployments causing incidents
  - Mean Time to Recovery : time to resolve deployment failures

Band thresholds (2023 report):
  Deployment Frequency:
    Elite  : On-demand / multiple per day
    High   : Between once per day and once per week
    Medium : Between once per week and once per month
    Low    : Less than once per month

  Lead Time:
    Elite  : < 1 hour
    High   : Between 1 day and 1 week  (using 1 hr – 1 week for precision)
    Medium : Between 1 week and 1 month
    Low    : > 6 months

  Change Failure Rate:
    Elite  : 0–5%
    High   : 5–10%
    Medium : 10–15%
    Low    : > 15%

  MTTR:
    Elite  : < 1 hour
    High   : < 1 day
    Medium : < 1 week
    Low    : > 1 week
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import text
from app.db.connection import get_engine
from app.core.logging import logger


# ── Band threshold functions ──────────────────────────────────────────────────

def df_band(deploys_per_day: float) -> str:
    """Deployment Frequency band from average deploys per day."""
    if deploys_per_day >= 1.0:   return "elite"   # ≥ 1/day
    if deploys_per_day >= 0.14:  return "high"    # ~1/week
    if deploys_per_day >= 0.033: return "medium"  # ~1/month
    return "low"


def lt_band(hours: Optional[float]) -> str:
    """Lead Time band from median hours."""
    if hours is None: return "insufficient_data"
    if hours < 1:       return "elite"    # < 1 hour
    if hours < 168:     return "high"     # < 1 week
    if hours < 720:     return "medium"   # < 1 month
    return "low"


def cfr_band(rate: Optional[float]) -> str:
    """Change Failure Rate band from ratio (0.0 – 1.0)."""
    if rate is None: return "insufficient_data"
    if rate <= 0.05:  return "elite"
    if rate <= 0.10:  return "high"
    if rate <= 0.15:  return "medium"
    return "low"


def mttr_band(hours: Optional[float]) -> str:
    """MTTR band from median hours."""
    if hours is None: return "insufficient_data"
    if hours < 1:    return "elite"    # < 1 hour
    if hours < 24:   return "high"     # < 1 day
    if hours < 168:  return "medium"   # < 1 week
    return "low"


def overall_band(bands: list[str]) -> str:
    """Overall DORA band = worst of the 4 metric bands."""
    order = ["insufficient_data", "low", "medium", "high", "elite"]
    valid = [b for b in bands if b in order]
    if not valid:
        return "insufficient_data"
    return min(valid, key=lambda b: order.index(b))


# ── Percentile helper ─────────────────────────────────────────────────────────

def percentile(values: list[float], p: float) -> Optional[float]:
    """
    Calculate percentile from a sorted list.
    p=50 → median, p=95 → p95
    MySQL 5.7/8 has PERCENTILE_CONT only in window functions.
    We compute in Python to support both MySQL versions.
    """
    if not values:
        return None
    sorted_v = sorted(values)
    n = len(sorted_v)
    idx = (p / 100) * (n - 1)
    lo, hi = int(idx), min(int(idx) + 1, n - 1)
    frac = idx - lo
    return sorted_v[lo] + frac * (sorted_v[hi] - sorted_v[lo])


# ── Per-project metric calculation ───────────────────────────────────────────

def calc_deployment_frequency(conn, project_id: str, window_start: date, window_end: date) -> dict:
    """
    Count successful production deployments per day in the window.
    Returns daily counts and 30-day rolling average deploys/day.
    """
    rows = conn.execute(text("""
        SELECT
            DATE(finished_at)       AS dep_date,
            COUNT(*)                AS total,
            SUM(result='SUCCESS')   AS successes,
            SUM(result='FAILURE')   AS failures
        FROM deployments
        WHERE project_id  = :pid
          AND environment  = 'PRODUCTION'
          AND finished_at  BETWEEN :start AND :end
        GROUP BY DATE(finished_at)
        ORDER BY dep_date
    """), {"pid": project_id, "start": window_start, "end": window_end}).fetchall()

    daily = {str(r.dep_date): {
        "total": r.total, "success": r.successes, "failure": r.failures
    } for r in rows}

    total_success = sum(r.successes for r in rows)
    window_days   = max((window_end - window_start).days, 1)
    deploys_per_day = total_success / window_days

    return {
        "daily":            daily,
        "total_success":    total_success,
        "deploys_per_day":  round(deploys_per_day, 4),
        "band":             df_band(deploys_per_day),
    }


def calc_lead_time(conn, project_id: str, window_start: date, window_end: date) -> dict:
    """
    Lead Time = time from first_commit_at on a branch → deployment to production.

    Requires:
      pull_requests.first_commit_at  (denormalised from commits table on insert)
      deployments.commit_sha          (links deployment to PR)

    Falls back to merged_at → deployed_at if first_commit_at is missing.
    """
    rows = conn.execute(text("""
        SELECT
            pr.id,
            pr.first_commit_at,
            pr.merged_at,
            d.finished_at                   AS deployed_at,
            TIMESTAMPDIFF(MINUTE,
                COALESCE(pr.first_commit_at, pr.merged_at),
                d.finished_at
            )                               AS lead_time_mins
        FROM pull_requests pr
        JOIN deployments d
            ON  d.project_id  = pr.project_id
            AND d.commit_sha  = pr.first_commit_sha
            AND d.environment = 'PRODUCTION'
            AND d.result      = 'SUCCESS'
        WHERE pr.project_id  = :pid
          AND pr.status       = 'MERGED'
          AND d.finished_at   BETWEEN :start AND :end
          AND TIMESTAMPDIFF(MINUTE,
                COALESCE(pr.first_commit_at, pr.merged_at),
                d.finished_at) > 0
        ORDER BY d.finished_at
    """), {"pid": project_id, "start": window_start, "end": window_end}).fetchall()

    if not rows:
        return {
            "sample_size":  0,
            "p50_hrs":      None,
            "p75_hrs":      None,
            "p95_hrs":      None,
            "band":         "insufficient_data",
            "note":         "No merged PRs linked to production deployments in window",
        }

    mins = [float(r.lead_time_mins) for r in rows if r.lead_time_mins is not None]
    hrs  = [m / 60 for m in mins]

    p50 = percentile(hrs, 50)
    p75 = percentile(hrs, 75)
    p95 = percentile(hrs, 95)

    return {
        "sample_size": len(hrs),
        "p50_hrs":     round(p50, 2) if p50 else None,
        "p75_hrs":     round(p75, 2) if p75 else None,
        "p95_hrs":     round(p95, 2) if p95 else None,
        "band":        lt_band(p50),
    }


def calc_change_failure_rate(conn, project_id: str,
                              window_start: date, window_end: date,
                              link_window_hours: int = 24) -> dict:
    """
    CFR = (deployments that caused a DORA-relevant incident) / (total deployments)

    Only incidents where cfr_include=1 count. The incident classifier sets this.
    An incident is attributed to a deployment if it started within
    link_window_hours after that deployment finished.
    """
    # Total production deployments in window
    dep_count = conn.execute(text("""
        SELECT COUNT(*) AS cnt
        FROM deployments
        WHERE project_id  = :pid
          AND environment  = 'PRODUCTION'
          AND finished_at  BETWEEN :start AND :end
    """), {"pid": project_id, "start": window_start, "end": window_end}).scalar()

    if not dep_count:
        return {
            "total_deployments": 0,
            "failed_deployments": 0,
            "rate": None,
            "band": "insufficient_data",
            "note": "No deployments in window",
        }

    # Deployments with a linked cfr_include incident
    failed_count = conn.execute(text("""
        SELECT COUNT(DISTINCT d.id) AS cnt
        FROM deployments d
        JOIN incidents i
            ON  i.project_id   = d.project_id
            AND i.cfr_include  = 1
            AND i.created_at   BETWEEN d.finished_at
                               AND DATE_ADD(d.finished_at,
                                   INTERVAL :window HOUR)
        WHERE d.project_id  = :pid
          AND d.environment  = 'PRODUCTION'
          AND d.finished_at  BETWEEN :start AND :end
    """), {
        "pid":    project_id,
        "start":  window_start,
        "end":    window_end,
        "window": link_window_hours,
    }).scalar()

    rate = failed_count / dep_count if dep_count else None

    return {
        "total_deployments":  dep_count,
        "failed_deployments": failed_count or 0,
        "rate":               round(rate, 4) if rate is not None else None,
        "rate_pct":           round(rate * 100, 2) if rate is not None else None,
        "band":               cfr_band(rate),
    }


def calc_mttr(conn, project_id: str, window_start: date, window_end: date) -> dict:
    """
    MTTR = median time from incident.created_at → incident.resolved_at
    Only for cfr_include=1 incidents (deployment failures, not infra/vendor).
    """
    rows = conn.execute(text("""
        SELECT
            id,
            created_at,
            resolved_at,
            TIMESTAMPDIFF(MINUTE, created_at, resolved_at) AS mttr_mins
        FROM incidents
        WHERE project_id  = :pid
          AND cfr_include  = 1
          AND resolved_at  IS NOT NULL
          AND created_at   BETWEEN :start AND :end
          AND TIMESTAMPDIFF(MINUTE, created_at, resolved_at) > 0
        ORDER BY created_at
    """), {"pid": project_id, "start": window_start, "end": window_end}).fetchall()

    if not rows:
        return {
            "sample_size": 0,
            "p50_hrs":     None,
            "p75_hrs":     None,
            "p95_hrs":     None,
            "band":        "insufficient_data",
            "note":        "No resolved deployment-failure incidents in window",
        }

    mins = [float(r.mttr_mins) for r in rows]
    hrs  = [m / 60 for m in mins]
    p50  = percentile(hrs, 50)
    p75  = percentile(hrs, 75)
    p95  = percentile(hrs, 95)

    return {
        "sample_size": len(hrs),
        "p50_hrs":     round(p50, 2) if p50 else None,
        "p75_hrs":     round(p75, 2) if p75 else None,
        "p95_hrs":     round(p95, 2) if p95 else None,
        "band":        mttr_band(p50),
    }


# ── Main entry points ─────────────────────────────────────────────────────────

def compute_project_dora(
    project_id:         str,
    window_days:        int = 90,
    link_window_hours:  int = 24,
) -> dict:
    """
    Compute all 4 DORA metrics for a project over the past window_days.
    Returns a rich dict suitable for the API + UI.
    Does NOT write to dora_daily — call materialise_dora_daily() for that.
    """
    engine      = get_engine()
    window_end  = date.today()
    window_start = window_end - timedelta(days=window_days)

    with engine.connect() as conn:
        df   = calc_deployment_frequency(conn, project_id, window_start, window_end)
        lt   = calc_lead_time(conn, project_id, window_start, window_end)
        cfr  = calc_change_failure_rate(conn, project_id, window_start, window_end, link_window_hours)
        mtr  = calc_mttr(conn, project_id, window_start, window_end)

    bands = [df["band"], lt["band"], cfr["band"], mtr["band"]]
    ob    = overall_band(bands)

    return {
        "project_id":    project_id,
        "window_days":   window_days,
        "window_start":  str(window_start),
        "window_end":    str(window_end),
        "computed_at":   datetime.now(timezone.utc).isoformat(),
        "overall_band":  ob,
        "metrics": {
            "deployment_frequency": {
                **df,
                "label": "Deployment Frequency",
                "unit":  "deploys/day",
            },
            "lead_time": {
                **lt,
                "label": "Lead Time for Changes",
                "unit":  "hours",
            },
            "change_failure_rate": {
                **cfr,
                "label": "Change Failure Rate",
                "unit":  "percent",
            },
            "mttr": {
                **mtr,
                "label": "Mean Time to Recovery",
                "unit":  "hours",
            },
        },
    }


def materialise_dora_daily(project_id: str, target_date: Optional[date] = None) -> int:
    """
    Compute DORA metrics for a single day and upsert into dora_daily.
    Called after every successful ingestion + nightly cron.
    Returns number of rows written.
    """
    if target_date is None:
        target_date = date.today()

    # Use a 30-day rolling window ending on target_date for daily row
    window_end   = target_date
    window_start = target_date - timedelta(days=30)

    engine = get_engine()

    with engine.connect() as conn:
        df  = calc_deployment_frequency(conn, project_id, window_start, window_end)
        lt  = calc_lead_time(conn, project_id, window_start, window_end)
        cfr = calc_change_failure_rate(conn, project_id, window_start, window_end)
        mtr = calc_mttr(conn, project_id, window_start, window_end)

    bands = [df["band"], lt["band"], cfr["band"], mtr["band"]]
    ob    = overall_band(bands)
    now   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:23]

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO dora_daily (
                project_id, metric_date,
                deployments_total, deployments_success, deployments_failed,
                df_band,
                lead_time_p50_hrs, lead_time_p75_hrs, lead_time_p95_hrs,
                lead_time_sample_size, lt_band,
                cfr_deployments, cfr_incidents, change_failure_rate, cfr_band,
                mttr_p50_hrs, mttr_p75_hrs, mttr_p95_hrs, mttr_sample_size, mttr_band,
                overall_band, computed_at
            ) VALUES (
                :pid, :mdate,
                :dep_total, :dep_success, :dep_failed,
                :df_band,
                :lt_p50, :lt_p75, :lt_p95,
                :lt_n, :lt_band,
                :cfr_dep, :cfr_inc, :cfr_rate, :cfr_band,
                :mtr_p50, :mtr_p75, :mtr_p95, :mtr_n, :mtr_band,
                :overall, :now
            )
            ON DUPLICATE KEY UPDATE
                deployments_total      = VALUES(deployments_total),
                deployments_success    = VALUES(deployments_success),
                deployments_failed     = VALUES(deployments_failed),
                df_band                = VALUES(df_band),
                lead_time_p50_hrs      = VALUES(lead_time_p50_hrs),
                lead_time_p75_hrs      = VALUES(lead_time_p75_hrs),
                lead_time_p95_hrs      = VALUES(lead_time_p95_hrs),
                lead_time_sample_size  = VALUES(lead_time_sample_size),
                lt_band                = VALUES(lt_band),
                cfr_deployments        = VALUES(cfr_deployments),
                cfr_incidents          = VALUES(cfr_incidents),
                change_failure_rate    = VALUES(change_failure_rate),
                cfr_band               = VALUES(cfr_band),
                mttr_p50_hrs           = VALUES(mttr_p50_hrs),
                mttr_p75_hrs           = VALUES(mttr_p75_hrs),
                mttr_p95_hrs           = VALUES(mttr_p95_hrs),
                mttr_sample_size       = VALUES(mttr_sample_size),
                mttr_band              = VALUES(mttr_band),
                overall_band           = VALUES(overall_band),
                computed_at            = VALUES(computed_at)
        """), {
            "pid":         project_id,
            "mdate":       target_date,
            "dep_total":   df.get("total_success", 0) + df.get("total_failure", 0),
            "dep_success": df.get("total_success", 0),
            "dep_failed":  cfr.get("failed_deployments", 0),
            "df_band":     df["band"],
            "lt_p50":      lt.get("p50_hrs"),
            "lt_p75":      lt.get("p75_hrs"),
            "lt_p95":      lt.get("p95_hrs"),
            "lt_n":        lt.get("sample_size", 0),
            "lt_band":     lt["band"],
            "cfr_dep":     cfr.get("total_deployments", 0),
            "cfr_inc":     cfr.get("failed_deployments", 0),
            "cfr_rate":    cfr.get("rate"),
            "cfr_band":    cfr["band"],
            "mtr_p50":     mtr.get("p50_hrs"),
            "mtr_p75":     mtr.get("p75_hrs"),
            "mtr_p95":     mtr.get("p95_hrs"),
            "mtr_n":       mtr.get("sample_size", 0),
            "mtr_band":    mtr["band"],
            "overall":     ob,
            "now":         now,
        })

    logger.info(f"dora_daily materialised: {project_id} / {target_date} / overall={ob}")
    return 1


def materialise_all_projects(window_days: int = 90) -> dict:
    """
    Nightly cron: recompute dora_daily for all projects × last window_days.
    """
    engine = get_engine()
    with engine.connect() as conn:
        projects = [r.id for r in conn.execute(text("SELECT id FROM projects")).fetchall()]

    results = {}
    today   = date.today()

    for pid in projects:
        written = 0
        for delta in range(window_days):
            d = today - timedelta(days=delta)
            try:
                materialise_dora_daily(pid, d)
                written += 1
            except Exception as e:
                logger.error(f"Failed materialising {pid}/{d}: {e}")
        results[pid] = written
        logger.info(f"Materialised {written} days for project: {pid}")

    return results
