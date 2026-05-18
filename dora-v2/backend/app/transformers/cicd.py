from app.models.payloads import PipelineRunRecord
from app.transformers.utils import to_utc_mysql, calc_duration, trunc

RESULT_MAP = {"SUCCESS":"SUCCESS","FAILURE":"FAILURE","ABORTED":"ABORTED","UNKNOWN":"FAILURE"}
ENV_MAP    = {"production":"PRODUCTION","prod":"PRODUCTION","staging":"STAGING",
              "stage":"STAGING","dev":"DEVELOPMENT","development":"DEVELOPMENT","test":"TEST"}


def transform_deployments(records: list[PipelineRunRecord], project_id: str) -> list[dict]:
    return [{
        "project_id":    project_id,
        "external_id":   r.pipeline_run_id,
        "pipeline_name": trunc(r.pipeline_name or r.pipeline_run_id),
        "environment":   ENV_MAP.get(r.environment.lower(), "PRODUCTION"),
        "result":        RESULT_MAP.get(r.status, "FAILURE"),
        "started_at":    to_utc_mysql(r.started_at),
        "finished_at":   to_utc_mysql(r.finished_at),
        "commit_sha":    r.commit_sha or "",
        "triggered_by":  trunc(r.triggered_by or ""),
        "duration_secs": calc_duration(r.started_at, r.finished_at),
    } for r in records]
