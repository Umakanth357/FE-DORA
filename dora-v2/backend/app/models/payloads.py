"""
Pydantic v2 validation models.
strict=True prevents silent type coercion hiding bad data.
All validators are per-record so one bad row never blocks the upload.
"""
import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator, model_validator

STRICT = {"strict": True, "str_strip_whitespace": True}

SCM_TOOLS   = {"github", "gitlab", "bitbucket", "azure_repos"}
CICD_TOOLS  = {"jenkins", "github_actions", "gitlab_ci", "circleci", "azure_pipelines"}
ITSM_TOOLS  = {"servicenow", "jira", "pagerduty", "opsgenie"}


def _ts(v: str) -> str:
    """Validate ISO 8601 timestamp — accepts Z, offsets, space separators."""
    if not v:
        raise ValueError("timestamp is empty")
    try:
        s = v.strip().replace(" ", "T")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if not re.search(r"[+-]\d{2}:\d{2}$", s):
            s += "+00:00"
        datetime.fromisoformat(s)
        return v
    except Exception:
        raise ValueError(f"Invalid ISO 8601 timestamp: {v!r}")


# ── Meta ──────────────────────────────────────────────────────────────────────

class MetaBlock(BaseModel):
    model_config = STRICT
    project_name:   str
    source_tool:    str
    collected_at:   str
    schema_version: str = "1.0"

    @field_validator("project_name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[a-z0-9][a-z0-9_-]*$", v):
            raise ValueError(
                f"project_name must be lowercase alphanumeric/hyphens/underscores, got {v!r}"
            )
        return v


# ── SCM ───────────────────────────────────────────────────────────────────────

class CommitRecord(BaseModel):
    model_config = STRICT
    sha:          str
    committed_at: str
    repo:         str
    author_name:  Optional[str] = None
    author_email: Optional[str] = None
    message:      Optional[str] = ""
    additions:    Optional[int] = 0
    deletions:    Optional[int] = 0
    branch:       Optional[str] = None

    @field_validator("sha")
    @classmethod
    def sha_ok(cls, v):
        if not v.strip():
            raise ValueError("sha is empty")
        return v.strip()

    @field_validator("committed_at")
    @classmethod
    def ts_ok(cls, v): return _ts(v)


class PRRecord(BaseModel):
    model_config = STRICT
    pr_id:            str
    created_at:       str
    repo:             str
    state:            str
    merged_at:        Optional[str] = None
    closed_at:        Optional[str] = None
    title:            Optional[str] = ""
    author:           Optional[str] = None
    base_branch:      Optional[str] = "main"
    head_branch:      Optional[str] = None
    first_commit_sha: Optional[str] = None
    first_commit_at:  Optional[str] = None

    @field_validator("state")
    @classmethod
    def state_ok(cls, v):
        allowed = {"open", "closed", "merged"}
        if v.lower() not in allowed:
            raise ValueError(f"state must be open/closed/merged, got {v!r}")
        return v.lower()

    @field_validator("created_at")
    @classmethod
    def ts1(cls, v): return _ts(v)

    @field_validator("merged_at", "closed_at", "first_commit_at")
    @classmethod
    def ts_opt(cls, v): return _ts(v) if v else v


class SCMPayload(BaseModel):
    model_config = STRICT
    meta:          MetaBlock
    commits:       list[CommitRecord] = []
    pull_requests: list[PRRecord]     = []

    @model_validator(mode="after")
    def check_tool(self):
        if self.meta.source_tool not in SCM_TOOLS:
            raise ValueError(f"source_tool must be one of {SCM_TOOLS}")
        return self


# ── CI/CD ─────────────────────────────────────────────────────────────────────

class PipelineRunRecord(BaseModel):
    model_config = STRICT
    pipeline_run_id: str
    started_at:      str
    finished_at:     str
    environment:     str
    status:          str
    pipeline_name:   Optional[str] = None
    type:            Optional[str] = "DEPLOYMENT"
    commit_sha:      Optional[str] = None
    triggered_by:    Optional[str] = None

    @field_validator("status")
    @classmethod
    def status_ok(cls, v):
        norm = v.upper()
        if norm not in {"SUCCESS", "FAILURE", "ABORTED", "UNKNOWN"}:
            raise ValueError(f"status must be SUCCESS/FAILURE/ABORTED, got {v!r}")
        return norm

    @field_validator("environment")
    @classmethod
    def env_ok(cls, v): return v.lower()

    @field_validator("started_at", "finished_at")
    @classmethod
    def ts_ok(cls, v): return _ts(v)


class CICDPayload(BaseModel):
    model_config = STRICT
    meta:          MetaBlock
    pipeline_runs: list[PipelineRunRecord] = []

    @model_validator(mode="after")
    def check_tool(self):
        if self.meta.source_tool not in CICD_TOOLS:
            raise ValueError(f"source_tool must be one of {CICD_TOOLS}")
        return self


# ── ITSM ──────────────────────────────────────────────────────────────────────

class IncidentRecord(BaseModel):
    model_config = STRICT
    issue_id:              str
    created_at:            str
    status:                str
    type:                  str       = "INCIDENT"
    title:                 Optional[str]       = ""
    severity:              Optional[str]       = "P2"
    resolved_at:           Optional[str]       = None
    description:           Optional[str]       = ""
    category:              Optional[str]       = ""
    labels:                Optional[list[str]] = None
    change_request_id:     Optional[str]       = None
    related_deployment_id: Optional[str]       = None
    service_affected:      Optional[str]       = None
    assignee:              Optional[str]       = None

    @field_validator("status")
    @classmethod
    def status_ok(cls, v):
        m = {"resolved":"RESOLVED","closed":"RESOLVED","open":"OPEN",
             "new":"OPEN","in_progress":"IN_PROGRESS","in progress":"IN_PROGRESS",
             "investigating":"IN_PROGRESS"}
        r = m.get(v.lower())
        if not r:
            raise ValueError(f"Unknown status {v!r}")
        return r

    @field_validator("severity")
    @classmethod
    def sev_ok(cls, v):
        if not v:
            return "P2"
        return v.upper() if v.upper() in {"P1","P2","P3","P4"} else "P2"

    @field_validator("type")
    @classmethod
    def type_ok(cls, v):
        if v.upper() != "INCIDENT":
            raise ValueError("type must be INCIDENT")
        return "INCIDENT"

    @field_validator("created_at")
    @classmethod
    def ts1(cls, v): return _ts(v)

    @field_validator("resolved_at")
    @classmethod
    def ts2(cls, v): return _ts(v) if v else v


class ITSMPayload(BaseModel):
    model_config = STRICT
    meta:      MetaBlock
    incidents: list[IncidentRecord] = []

    @model_validator(mode="after")
    def check_tool(self):
        if self.meta.source_tool not in ITSM_TOOLS:
            raise ValueError(f"source_tool must be one of {ITSM_TOOLS}")
        return self
