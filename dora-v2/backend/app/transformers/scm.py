from app.models.payloads import CommitRecord, PRRecord
from app.transformers.utils import to_utc_mysql, trunc

PR_STATUS = {"merged": "MERGED", "closed": "CLOSED", "open": "OPEN"}


def transform_commits(records: list[CommitRecord], project_id: str) -> list[dict]:
    return [{
        "project_id":   project_id,
        "sha":          r.sha,
        "author_name":  trunc(r.author_name or "unknown"),
        "author_email": trunc(r.author_email or ""),
        "committed_at": to_utc_mysql(r.committed_at),
        "message":      trunc(r.message or "", 500),
        "additions":    r.additions or 0,
        "deletions":    r.deletions or 0,
        "branch":       trunc(r.branch or ""),
    } for r in records]


def transform_pull_requests(records: list[PRRecord], project_id: str,
                             commit_map: dict = None) -> list[dict]:
    """
    commit_map: {sha -> committed_at} built from commits uploaded in same batch.
    Used to populate first_commit_at for Lead Time calculation.
    """
    commit_map = commit_map or {}
    rows = []
    for r in records:
        first_commit_at = None
        if r.first_commit_at:
            first_commit_at = to_utc_mysql(r.first_commit_at)
        elif r.first_commit_sha and r.first_commit_sha in commit_map:
            first_commit_at = to_utc_mysql(commit_map[r.first_commit_sha])

        rows.append({
            "project_id":       project_id,
            "external_id":      r.pr_id,
            "title":            trunc(r.title or "", 500),
            "status":           PR_STATUS.get(r.state, "OPEN"),
            "author":           trunc(r.author or ""),
            "base_branch":      trunc(r.base_branch or "main"),
            "head_branch":      trunc(r.head_branch or ""),
            "created_at":       to_utc_mysql(r.created_at),
            "merged_at":        to_utc_mysql(r.merged_at),
            "closed_at":        to_utc_mysql(r.closed_at),
            "first_commit_sha": r.first_commit_sha,
            "first_commit_at":  first_commit_at,
        })
    return rows
