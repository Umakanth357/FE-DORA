"""
DORA Platform Test Suite
Run: python -m pytest tests/ -v
All tests are pure-Python, no DB or network required.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.transformers.utils import to_utc_mysql, calc_duration, calc_mttr_minutes
from app.core.metrics import df_band, lt_band, cfr_band, mttr_band, overall_band, percentile
from app.core.classifier import classify_incident, classify_batch


# ── Timestamp normalisation ───────────────────────────────────────────────────

class TestTimestamps:
    def test_iso_z(self):
        assert to_utc_mysql("2024-01-10T14:23:00Z") == "2024-01-10 14:23:00.000"

    def test_iso_offset_positive(self):
        assert to_utc_mysql("2024-01-10T19:53:00+05:30") == "2024-01-10 14:23:00.000"

    def test_iso_offset_negative(self):
        assert to_utc_mysql("2024-01-10T09:23:00-05:00") == "2024-01-10 14:23:00.000"

    def test_space_separator(self):
        assert to_utc_mysql("2024-01-10 14:23:00") == "2024-01-10 14:23:00.000"

    def test_unix_epoch_int_seconds(self):
        result = to_utc_mysql(1704896580)
        assert result.startswith("2024-01-10")

    def test_unix_epoch_string_ms(self):
        result = to_utc_mysql("1704896580000")
        assert result.startswith("2024-01-10")

    def test_none_returns_none(self):
        assert to_utc_mysql(None) is None

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            to_utc_mysql("not-a-date")

    def test_no_tz_assumed_utc(self):
        # No timezone info → assumed UTC
        result = to_utc_mysql("2024-06-15T10:00:00")
        assert result == "2024-06-15 10:00:00.000"


class TestDuration:
    def test_basic(self):
        d = calc_duration("2024-01-10T10:00:00Z", "2024-01-10T10:08:00Z")
        assert d == 480

    def test_none_if_missing(self):
        assert calc_duration(None, "2024-01-10T10:00:00Z") is None
        assert calc_duration("2024-01-10T10:00:00Z", None) is None

    def test_mttr_minutes(self):
        m = calc_mttr_minutes("2024-01-10T02:00:00Z", "2024-01-10T04:30:00Z")
        assert m == 150


# ── DORA Band logic ───────────────────────────────────────────────────────────

class TestDFBand:
    def test_elite(self):   assert df_band(2.0)   == "elite"
    def test_high(self):    assert df_band(0.5)   == "high"
    def test_weekly(self):  assert df_band(0.14)  == "high"
    def test_medium(self):  assert df_band(0.05)  == "medium"
    def test_low(self):     assert df_band(0.01)  == "low"


class TestLTBand:
    def test_elite(self):   assert lt_band(0.5)   == "elite"    # 30 min
    def test_high_hrs(self):assert lt_band(4.0)   == "high"     # 4 hours
    def test_high_days(self):assert lt_band(48.0) == "high"     # 2 days
    def test_medium(self):  assert lt_band(300.0) == "medium"   # ~12 days
    def test_low(self):     assert lt_band(800.0) == "low"      # >1 month
    def test_none(self):    assert lt_band(None)  == "insufficient_data"


class TestCFRBand:
    def test_elite(self):   assert cfr_band(0.02) == "elite"
    def test_boundary(self):assert cfr_band(0.05) == "elite"   # 5% = elite
    def test_high(self):    assert cfr_band(0.08) == "high"
    def test_medium(self):  assert cfr_band(0.12) == "medium"
    def test_low(self):     assert cfr_band(0.20) == "low"
    def test_none(self):    assert cfr_band(None) == "insufficient_data"


class TestMTTRBand:
    def test_elite(self):   assert mttr_band(0.5)  == "elite"   # 30 min
    def test_high(self):    assert mttr_band(2.0)  == "high"    # 2 hrs
    def test_high_20h(self):assert mttr_band(20.0) == "high"    # 20 hrs
    def test_medium(self):  assert mttr_band(50.0) == "medium"  # 2 days
    def test_low(self):     assert mttr_band(200.0)== "low"     # >1 week
    def test_none(self):    assert mttr_band(None) == "insufficient_data"


class TestOverallBand:
    def test_all_elite(self):
        assert overall_band(["elite","elite","elite","elite"]) == "elite"

    def test_worst_wins(self):
        assert overall_band(["elite","high","medium","elite"]) == "medium"

    def test_low_wins(self):
        assert overall_band(["high","high","high","low"]) == "low"

    def test_insufficient_data(self):
        assert overall_band(["insufficient_data","elite","elite","elite"]) == "insufficient_data"

    def test_empty(self):
        assert overall_band([]) == "insufficient_data"


class TestPercentile:
    def test_p50_even(self):
        vals = list(range(1, 11))  # 1..10
        assert abs(percentile(vals, 50) - 5.5) < 0.01

    def test_p95(self):
        vals = list(range(1, 101))  # 1..100
        p95 = percentile(vals, 95)
        assert 94 < p95 < 96

    def test_single_value(self):
        assert percentile([42], 50) == 42

    def test_empty(self):
        assert percentile([], 50) is None


# ── Incident Classifier ───────────────────────────────────────────────────────

class TestClassifier:
    def test_explicit_deployment_link(self):
        r = classify_incident("Payment service down", deployment_id="build-1234")
        assert r.classification == "DEPLOYMENT_FAILURE"
        assert r.dora_relevant is True
        assert r.confidence >= 80

    def test_change_request_link(self):
        r = classify_incident("Auth broken", change_request_id="CHG0012345")
        assert r.classification == "DEPLOYMENT_FAILURE"
        assert r.confidence >= 70

    def test_category_software(self):
        r = classify_incident("Users cannot login", category="Software")
        assert r.classification == "DEPLOYMENT_FAILURE"

    def test_keyword_deployment(self):
        r = classify_incident("Regression after this morning's release")
        assert r.classification == "DEPLOYMENT_FAILURE"

    def test_keyword_hotfix(self):
        r = classify_incident("Hotfix needed after deployment broke auth")
        assert r.classification == "DEPLOYMENT_FAILURE"

    def test_aws_outage(self):
        r = classify_incident("AWS us-east-1 network outage", category="Network")
        assert r.classification == "INFRASTRUCTURE"
        assert r.dora_relevant is False

    def test_vendor(self):
        r = classify_incident("Stripe payment gateway down", category="Vendor")
        assert r.classification == "EXTERNAL_DEPENDENCY"
        assert r.dora_relevant is False

    def test_security(self):
        r = classify_incident("Security breach detected", category="Security")
        assert r.classification == "SECURITY"
        assert r.dora_relevant is False

    def test_disk_full(self):
        r = classify_incident("Database disk full", description="storage at 100%",
                               category="Storage")
        assert r.classification == "INFRASTRUCTURE"
        assert r.dora_relevant is False

    def test_other_no_signal(self):
        r = classify_incident("Office printer not working")
        assert r.classification == "OTHER"
        assert r.dora_relevant is False

    def test_label_deployment(self):
        r = classify_incident("Service degraded", labels=["deployment", "regression"])
        assert r.classification == "DEPLOYMENT_FAILURE"

    def test_cfr_include_respects_confidence(self):
        # Low confidence deployment failure should still be flagged for review
        r = classify_incident("Something broke", threshold=40)
        # If confidence < 40 with no signals, cfr_include should be False
        if r.confidence < 40:
            assert r.cfr_include is False

    def test_batch_classification(self):
        incidents = [
            {"issue_id":"INC001","title":"Deploy broke prod","category":"Software",
             "created_at":"2024-01-10T14:00:00Z","status":"resolved"},
            {"issue_id":"INC002","title":"AWS network issue","category":"Network",
             "created_at":"2024-01-11T09:00:00Z","status":"resolved"},
        ]
        result = classify_batch(incidents)
        assert result[0]["_classification"] == "DEPLOYMENT_FAILURE"
        assert result[0]["_dora_relevant"] is True
        assert result[1]["_classification"] == "INFRASTRUCTURE"
        assert result[1]["_dora_relevant"] is False


# ── SCM Transformer ───────────────────────────────────────────────────────────

class TestSCMTransformer:
    def setup_method(self):
        from app.models.payloads import CommitRecord, PRRecord
        self.CommitRecord = CommitRecord
        self.PRRecord = PRRecord
        from app.transformers.scm import transform_commits, transform_pull_requests
        self.transform_commits = transform_commits
        self.transform_pull_requests = transform_pull_requests

    def _commit(self, **kw):
        return self.CommitRecord(**{
            "sha":"abc123","committed_at":"2024-01-10T14:23:00Z","repo":"org/repo",
            **kw
        })

    def test_commit_project_id(self):
        rows = self.transform_commits([self._commit()], "my-project")
        assert rows[0]["project_id"] == "my-project"

    def test_commit_timestamp_utc(self):
        rows = self.transform_commits([self._commit()], "p")
        assert rows[0]["committed_at"] == "2024-01-10 14:23:00.000"

    def test_commit_message_truncated(self):
        rows = self.transform_commits([self._commit(message="x"*600)], "p")
        assert len(rows[0]["message"]) == 500

    def _pr(self, **kw):
        return self.PRRecord(**{
            "pr_id":"42","created_at":"2024-01-08T09:00:00Z","repo":"org/repo",
            "state":"merged","merged_at":"2024-01-10T16:45:00Z",
            **kw
        })

    def test_pr_status_merged(self):
        rows = self.transform_pull_requests([self._pr()], "p")
        assert rows[0]["status"] == "MERGED"

    def test_pr_first_commit_from_map(self):
        # first_commit_at should be populated from commit_map when not explicit
        pr = self._pr(first_commit_sha="abc123")
        rows = self.transform_pull_requests([pr], "p",
               commit_map={"abc123": "2024-01-07T10:00:00Z"})
        assert rows[0]["first_commit_at"] is not None


# ── CI/CD Transformer ─────────────────────────────────────────────────────────

class TestCICDTransformer:
    def setup_method(self):
        from app.models.payloads import PipelineRunRecord
        from app.transformers.cicd import transform_deployments
        self.PipelineRunRecord = PipelineRunRecord
        self.transform = transform_deployments

    def _run(self, **kw):
        return self.PipelineRunRecord(**{
            "pipeline_run_id":"build-99",
            "started_at":"2024-01-10T17:00:00Z",
            "finished_at":"2024-01-10T17:08:00Z",
            "environment":"production", "status":"SUCCESS",
            **kw
        })

    def test_result_success(self):
        rows = self.transform([self._run()], "p")
        assert rows[0]["result"] == "SUCCESS"

    def test_env_normalised(self):
        rows = self.transform([self._run(environment="prod")], "p")
        assert rows[0]["environment"] == "PRODUCTION"

    def test_duration_computed(self):
        rows = self.transform([self._run()], "p")
        assert rows[0]["duration_secs"] == 480  # 8 minutes

    def test_failure_mapped(self):
        rows = self.transform([self._run(status="FAILURE")], "p")
        assert rows[0]["result"] == "FAILURE"

    def test_unknown_mapped_to_failure(self):
        rows = self.transform([self._run(status="UNKNOWN")], "p")
        assert rows[0]["result"] == "FAILURE"
