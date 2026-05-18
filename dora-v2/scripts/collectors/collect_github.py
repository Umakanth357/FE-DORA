#!/usr/bin/env python3
"""
GitHub SCM Collector
====================
Collects commits and pull requests from a GitHub repository.
Outputs: scm_data.json

TOKEN PERMISSIONS REQUIRED:
  Fine-grained PAT: Contents (read), Pull requests (read), Metadata (read)
  Classic PAT scope: repo  (or public_repo for public repos)

CREATE TOKEN:
  github.com → Settings → Developer settings → Personal access tokens

USAGE:
  pip install requests
  python collect_github.py --token ghp_xxx --repo org/repo --project myapp
  python collect_github.py --token ghp_xxx --repo org/repo --project myapp --days 365
"""
import argparse, json, sys, time
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    sys.exit("ERROR: pip install requests")

DEFAULT_PROJECT = "__PROJECT_NAME__"
DEFAULT_DAYS    = __DAYS__


def gh(url, token, params=None):
    r = requests.get(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }, params=params, timeout=30)
    if r.status_code == 401: sys.exit("ERROR: Invalid GitHub token")
    if r.status_code == 403:
        reset = r.headers.get("X-RateLimit-Reset", "?")
        sys.exit(f"ERROR: Rate limited. Reset at Unix time {reset}")
    r.raise_for_status()
    return r.json()


def fetch_commits(repo, token, since):
    print("  Fetching commits...", end="", flush=True)
    commits, page = [], 1
    while True:
        data = gh(f"https://api.github.com/repos/{repo}/commits", token,
                  {"since": since, "per_page": 100, "page": page})
        if not data: break
        for c in data:
            a = c.get("commit", {}).get("author", {})
            commits.append({
                "sha":          c["sha"],
                "author_name":  a.get("name", ""),
                "author_email": a.get("email", ""),
                "committed_at": a.get("date", ""),
                "message":      c.get("commit", {}).get("message", ""),
                "repo":         repo,
                "additions":    0,
                "deletions":    0,
            })
        if len(data) < 100: break
        page += 1
        time.sleep(0.1)
    print(f" {len(commits)} found")
    return commits


def fetch_prs(repo, token, since):
    print("  Fetching pull requests...", end="", flush=True)
    prs, page = [], 1
    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    while True:
        data = gh(f"https://api.github.com/repos/{repo}/pulls", token,
                  {"state":"all","sort":"updated","direction":"desc","per_page":100,"page":page})
        if not data: break
        stop = False
        for pr in data:
            upd = pr.get("updated_at", "")
            if upd and datetime.fromisoformat(upd.replace("Z","+00:00")) < since_dt:
                stop = True; break
            head_sha = pr.get("head", {}).get("sha")
            prs.append({
                "pr_id":            str(pr["number"]),
                "title":            pr.get("title", ""),
                "state":            "merged" if pr.get("merged_at") else pr.get("state","open"),
                "author":           pr.get("user", {}).get("login", ""),
                "base_branch":      pr.get("base", {}).get("ref", "main"),
                "head_branch":      pr.get("head", {}).get("ref", ""),
                "created_at":       pr.get("created_at", ""),
                "merged_at":        pr.get("merged_at"),
                "closed_at":        pr.get("closed_at"),
                "repo":             repo,
                "first_commit_sha": head_sha,
            })
        if stop or len(data) < 100: break
        page += 1
        time.sleep(0.1)
    print(f" {len(prs)} found")
    return prs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--token",   required=True)
    p.add_argument("--repo",    required=True, help="org/repo format")
    p.add_argument("--project", default=DEFAULT_PROJECT)
    p.add_argument("--days",    type=int, default=DEFAULT_DAYS)
    p.add_argument("--output",  default="scm_data.json")
    a = p.parse_args()

    since = (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\nGitHub SCM Collector  |  {a.repo}  |  project={a.project}  |  last {a.days} days\n")

    try: gh("https://api.github.com/user", a.token)
    except Exception as e: sys.exit(f"Auth failed: {e}")

    commits = fetch_commits(a.repo, a.token, since)
    prs     = fetch_prs(a.repo, a.token, since)

    out = {
        "meta": {"project_name": a.project, "source_tool": "github",
                 "collected_at": datetime.now(timezone.utc).isoformat(),
                 "schema_version": "1.0"},
        "commits": commits, "pull_requests": prs,
    }
    with open(a.output, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\n✓  {len(commits)} commits,  {len(prs)} pull requests")
    print(f"✓  Saved to {a.output}")
    print(f"\n→  Upload {a.output} to the DORA portal\n")


if __name__ == "__main__":
    main()
