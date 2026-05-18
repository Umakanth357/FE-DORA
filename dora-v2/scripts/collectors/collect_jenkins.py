#!/usr/bin/env python3
"""
Jenkins CI/CD Collector
=======================
Extracts build/deployment runs from a Jenkins job.
Outputs: cicd_data.json

TOKEN PERMISSIONS REQUIRED:
  Jenkins user with Job: Read permission on the target job.
  API Token (NOT your password).

CREATE API TOKEN:
  Jenkins → Your name (top right) → Configure → API Token → Add new Token

USAGE:
  pip install requests
  python collect_jenkins.py \
    --url https://jenkins.company.com \
    --user admin --token YOUR_API_TOKEN \
    --job deploy-production --project myapp

  # Folder-scoped jobs use / separator:
  python collect_jenkins.py ... --job "Platform/deploy-production"
"""
import argparse, json, sys
from datetime import datetime, timedelta, timezone

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    sys.exit("ERROR: pip install requests")

DEFAULT_PROJECT = "__PROJECT_NAME__"
DEFAULT_DAYS    = __DAYS__


def jget(url, auth):
    r = requests.get(url, auth=auth, timeout=30)
    if r.status_code == 401: sys.exit("ERROR: Invalid credentials")
    if r.status_code == 403: sys.exit("ERROR: Missing Job:Read permission")
    if r.status_code == 404: sys.exit(f"ERROR: Not found: {url}")
    r.raise_for_status()
    return r.json()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url",         required=True, help="Jenkins base URL")
    p.add_argument("--user",        required=True)
    p.add_argument("--token",       required=True, help="Jenkins API token")
    p.add_argument("--job",         required=True, help="Job name (use / for folder: Folder/Job)")
    p.add_argument("--project",     default=DEFAULT_PROJECT)
    p.add_argument("--days",        type=int, default=DEFAULT_DAYS)
    p.add_argument("--environment", default="production")
    p.add_argument("--output",      default="cicd_data.json")
    a = p.parse_args()

    auth      = HTTPBasicAuth(a.user, a.token)
    since_ts  = (datetime.now(timezone.utc) - timedelta(days=a.days)).timestamp()
    job_path  = "/job/".join(a.job.split("/"))
    base_url  = a.url.rstrip("/")

    print(f"\nJenkins CI/CD Collector  |  job={a.job}  |  project={a.project}  |  last {a.days} days\n")

    # Verify connection
    try: jget(f"{base_url}/api/json", auth)
    except SystemExit: raise
    except Exception as e: sys.exit(f"Cannot connect: {e}")

    print("  Fetching builds...", end="", flush=True)
    job_data = jget(
        f"{base_url}/job/{job_path}/api/json"
        "?tree=builds[number,result,timestamp,duration,url,actions[lastBuiltRevision[SHA1]]]",
        auth
    )

    runs = []
    for b in job_data.get("builds", []):
        ts_ms = b.get("timestamp", 0)
        if ts_ms / 1000 < since_ts:
            continue

        started  = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        dur_ms   = b.get("duration", 0)
        finished = datetime.fromtimestamp((ts_ms + dur_ms) / 1000, tz=timezone.utc)
        result   = (b.get("result") or "UNKNOWN").upper()
        if result not in ("SUCCESS","FAILURE","ABORTED"):
            result = "UNKNOWN"

        commit_sha = None
        for action in b.get("actions", []):
            rev = action.get("lastBuiltRevision", {})
            if rev.get("SHA1"):
                commit_sha = rev["SHA1"]
                break

        runs.append({
            "pipeline_run_id": f"{a.job.replace('/','-')}-{b['number']}",
            "pipeline_name":   a.job,
            "environment":     a.environment,
            "status":          result,
            "type":            "DEPLOYMENT",
            "started_at":      started.isoformat(),
            "finished_at":     finished.isoformat(),
            "commit_sha":      commit_sha,
            "triggered_by":    None,
        })

    print(f" {len(runs)} builds found")

    out = {
        "meta": {"project_name": a.project, "source_tool": "jenkins",
                 "collected_at": datetime.now(timezone.utc).isoformat(),
                 "schema_version": "1.0"},
        "pipeline_runs": runs,
    }
    with open(a.output, "w") as f:
        json.dump(out, f, indent=2)

    success = sum(1 for r in runs if r["status"] == "SUCCESS")
    failure = sum(1 for r in runs if r["status"] == "FAILURE")
    print(f"\n✓  {len(runs)} runs  ({success} success / {failure} failure)")
    print(f"✓  Saved to {a.output}")
    print(f"\n→  Upload {a.output} to the DORA portal\n")


if __name__ == "__main__":
    main()
