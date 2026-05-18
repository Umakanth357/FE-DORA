-- ============================================================
-- DORA Platform — Complete Schema
-- Version: 1.0
-- No DevLake dependency. Owned entirely by this platform.
-- ============================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ── 1. Projects ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
    id           VARCHAR(100)  NOT NULL,
    display_name VARCHAR(255)  NOT NULL,
    description  TEXT,
    team         VARCHAR(255),
    created_at   DATETIME(3)   NOT NULL,
    updated_at   DATETIME(3)   NOT NULL,
    PRIMARY KEY (id),
    INDEX idx_team (team)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 2. Commits ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS commits (
    id            BIGINT        NOT NULL AUTO_INCREMENT,
    project_id    VARCHAR(100)  NOT NULL,
    sha           VARCHAR(40)   NOT NULL,
    author_name   VARCHAR(255),
    author_email  VARCHAR(255),
    committed_at  DATETIME(3)   NOT NULL,
    message       TEXT,
    additions     INT           DEFAULT 0,
    deletions     INT           DEFAULT 0,
    branch        VARCHAR(255),
    PRIMARY KEY (id),
    UNIQUE KEY uq_project_sha (project_id, sha),
    INDEX idx_committed   (project_id, committed_at),
    CONSTRAINT fk_commits_project FOREIGN KEY (project_id) REFERENCES projects(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 3. Pull Requests ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pull_requests (
    id                 BIGINT        NOT NULL AUTO_INCREMENT,
    project_id         VARCHAR(100)  NOT NULL,
    external_id        VARCHAR(255)  NOT NULL,
    title              VARCHAR(500),
    status             ENUM('OPEN','MERGED','CLOSED') NOT NULL DEFAULT 'OPEN',
    author             VARCHAR(255),
    base_branch        VARCHAR(255),
    head_branch        VARCHAR(255),
    created_at         DATETIME(3)   NOT NULL,
    merged_at          DATETIME(3),
    closed_at          DATETIME(3),
    first_commit_sha   VARCHAR(40),
    -- Denormalised for faster Lead Time query
    first_commit_at    DATETIME(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_project_pr  (project_id, external_id),
    INDEX idx_merged          (project_id, merged_at),
    INDEX idx_first_commit    (project_id, first_commit_sha),
    CONSTRAINT fk_pr_project FOREIGN KEY (project_id) REFERENCES projects(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 4. Deployments ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS deployments (
    id             BIGINT        NOT NULL AUTO_INCREMENT,
    project_id     VARCHAR(100)  NOT NULL,
    external_id    VARCHAR(255)  NOT NULL,
    pipeline_name  VARCHAR(255),
    environment    ENUM('PRODUCTION','STAGING','DEVELOPMENT','TEST') NOT NULL DEFAULT 'PRODUCTION',
    result         ENUM('SUCCESS','FAILURE','ABORTED') NOT NULL,
    started_at     DATETIME(3)   NOT NULL,
    finished_at    DATETIME(3),
    commit_sha     VARCHAR(40),
    triggered_by   VARCHAR(255),
    -- Computed on insert via trigger / application logic
    duration_secs  INT,
    PRIMARY KEY (id),
    UNIQUE KEY uq_project_run  (project_id, external_id),
    INDEX idx_finished         (project_id, environment, result, finished_at),
    INDEX idx_commit_sha       (project_id, commit_sha),
    CONSTRAINT fk_dep_project FOREIGN KEY (project_id) REFERENCES projects(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 5. Incidents ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents (
    id                        BIGINT        NOT NULL AUTO_INCREMENT,
    project_id                VARCHAR(100)  NOT NULL,
    external_id               VARCHAR(255)  NOT NULL,
    title                     VARCHAR(500),
    severity                  ENUM('P1','P2','P3','P4') DEFAULT 'P2',
    status                    ENUM('OPEN','IN_PROGRESS','RESOLVED') DEFAULT 'OPEN',

    -- Classification (populated by classifier engine)
    classification            ENUM('DEPLOYMENT_FAILURE','INFRASTRUCTURE',
                                   'EXTERNAL_DEPENDENCY','SECURITY','OTHER')
                              DEFAULT 'OTHER',
    classification_confidence TINYINT       DEFAULT 0,   -- 0-100
    dora_relevant             TINYINT(1)    DEFAULT 0,
    cfr_include               TINYINT(1)    DEFAULT 0,
    needs_review              TINYINT(1)    DEFAULT 0,
    reviewed_by               VARCHAR(255),
    reviewed_at               DATETIME(3),

    -- Timing
    created_at                DATETIME(3)   NOT NULL,
    resolved_at               DATETIME(3),
    mttr_minutes              INT,           -- computed on upsert

    -- Deployment link
    linked_deployment_id      BIGINT,
    link_method               ENUM('explicit','time_window','unlinked') DEFAULT 'unlinked',

    -- Raw fields for classifier (stored for re-classification)
    raw_category              VARCHAR(255),
    raw_labels                JSON,
    change_request_id         VARCHAR(255),
    service_affected          VARCHAR(255),
    assignee                  VARCHAR(255),

    PRIMARY KEY (id),
    UNIQUE KEY uq_project_inc (project_id, external_id),
    INDEX idx_created         (project_id, dora_relevant, created_at),
    INDEX idx_cfr             (project_id, cfr_include, created_at),
    INDEX idx_review          (project_id, needs_review),
    CONSTRAINT fk_inc_project FOREIGN KEY (project_id) REFERENCES projects(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 6. DORA Daily Metrics (materialised, Grafana/UI reads this) ──
CREATE TABLE IF NOT EXISTS dora_daily (
    project_id               VARCHAR(100)  NOT NULL,
    metric_date              DATE          NOT NULL,

    -- Deployment Frequency
    deployments_total        INT           DEFAULT 0,
    deployments_success      INT           DEFAULT 0,
    deployments_failed       INT           DEFAULT 0,
    df_band                  ENUM('elite','high','medium','low','insufficient_data'),

    -- Lead Time for Changes (hours)
    lead_time_p50_hrs        DECIMAL(10,2),
    lead_time_p75_hrs        DECIMAL(10,2),
    lead_time_p95_hrs        DECIMAL(10,2),
    lead_time_sample_size    INT           DEFAULT 0,
    lt_band                  ENUM('elite','high','medium','low','insufficient_data'),

    -- Change Failure Rate
    cfr_deployments          INT           DEFAULT 0,
    cfr_incidents            INT           DEFAULT 0,
    change_failure_rate      DECIMAL(7,4),  -- 0.0000 to 1.0000
    cfr_band                 ENUM('elite','high','medium','low','insufficient_data'),

    -- Mean Time to Recovery (hours)
    mttr_p50_hrs             DECIMAL(10,2),
    mttr_p75_hrs             DECIMAL(10,2),
    mttr_p95_hrs             DECIMAL(10,2),
    mttr_sample_size         INT           DEFAULT 0,
    mttr_band                ENUM('elite','high','medium','low','insufficient_data'),

    -- Overall DORA level (worst of 4)
    overall_band             ENUM('elite','high','medium','low','insufficient_data'),

    computed_at              DATETIME(3)   NOT NULL,

    PRIMARY KEY (project_id, metric_date),
    INDEX idx_date           (metric_date),
    CONSTRAINT fk_daily_project FOREIGN KEY (project_id) REFERENCES projects(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 7. Ingestion Runs (audit log) ────────────────────────────
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id                BIGINT        NOT NULL AUTO_INCREMENT,
    project_id        VARCHAR(100)  NOT NULL,
    file_type         ENUM('scm','cicd','itsm') NOT NULL,
    source_tool       VARCHAR(100),
    records_inserted  INT           DEFAULT 0,
    records_updated   INT           DEFAULT 0,
    records_skipped   INT           DEFAULT 0,
    errors_json       JSON,
    duration_ms       INT,
    created_at        DATETIME(3)   NOT NULL,
    PRIMARY KEY (id),
    INDEX idx_project  (project_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 8. Incident Review Queue (human overrides) ───────────────
CREATE TABLE IF NOT EXISTS incident_reviews (
    id              BIGINT        NOT NULL AUTO_INCREMENT,
    incident_id     BIGINT        NOT NULL,
    project_id      VARCHAR(100)  NOT NULL,
    original_class  VARCHAR(50),
    new_class       VARCHAR(50),
    reviewer        VARCHAR(255),
    notes           TEXT,
    reviewed_at     DATETIME(3)   NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_review_incident FOREIGN KEY (incident_id) REFERENCES incidents(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
