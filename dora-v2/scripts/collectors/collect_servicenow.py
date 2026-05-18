#!/usr/bin/env python3
"""
ServiceNow Incident Collector
==============================
Extracts incidents with full classification-support fields.
Outputs: incidents_data.json

PERMISSIONS REQUIRED:
  ServiceNow user with 'itil' role (read-only on incident table).
  Recommended: create a dedicated API service account.

USAGE:
  pip install requests
  python collect_servicenow.py \
    --instance company.service-now.com \
    --user api_user --password secret \
    --project myapp --days 180

  # Filter by priority and assignment group:
  python collect_servicenow.py ... --priority 1,2 --group "Platform Engineering"
"""
import argparse, json, sys
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    sys.exit("ERROR: pip install requests")

DEFAULT_PROJECT = "__PROJECT_NAME__"
DEFAULT_DAYS    = __DAYS__

PRIORITY_MAP = {"1":"P1","2":"P2","3":"P3","4":"P4"}
STATE_MAP    = {"1":"OPEN","2":"IN_PROGRESS","3":"IN_PROGRESS",
                "6":"RESOLVED","7":"RESOLVED"}


def sn_get(instance, table, auth, params):
    url  = f"https://{instance}/api/now/table/{table}"
    r    = requests.get(url, auth=auth,
                        headers={"Accept":"application/json"},
                        params=params, timeout=30)
    if r.status_code == 401: sys.exit("ERROR: Invalid credentials")
    if r.status_code == 403: sys.exit("ERROR: Need itil role")
    r.raise_for_status()
    return r.json().get("result", [])


def sn_ts(ts: str) -> Optional[str]:
    if not ts or not ts.strip(): return None
    try:
        return datetime.strptime(ts.strip(), "%Y-%m-%d %H:%M:%S") \
                       .replace(tzinfo=timezone.utc).isoformat()
    except ValueError: return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--instance", required=True, help="e.g. company.service-now.com")
    p.add_argument("--user",     required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--project",  default=DEFAULT_PROJECT)
    p.add_argument("--days",     type=int, default=DEFAULT_DAYS)
    p.add_argument("--priority", default="1,2", help="Comma list: 1,2,3")
    p.add_argument("--group",    default=None,  help="Assignment group name filter")
    p.add_argument("--output",   default="incidents_data.json")
    a = p.parse_args()

    auth       = HTTPBasicAuth(a.user, a.password)
    priorities = [x.strip() for x in a.priority.split(",")]
    since      = (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%d")

    print(f"\nServiceNow Collector  |  {a.instance}  |  project={a.project}  |  last {a.days} days\n")

    # Verify
    try: sn_get(a.instance, "incident", auth, {"sysparm_limit": 1})
    except SystemExit: raise
    except Exception as e: sys.exit(f"Cannot connect: {e}")

    query = f"sys_created_on>={since}^priority IN {','.join(priorities)}"
    if a.group: query += f"^assignment_group.name={a.group}"

    print("  Fetching incidents...", end="", flush=True)
    records = sn_get(a.instance, "incident", auth, {
        "sysparm_query":  query,
        "sysparm_fields": ("sys_id,number,short_description,description,priority,state,"
                           "category,subcategory,sys_created_on,resolved_at,closed_at,"
                           "assignment_group,assigned_to,cmdb_ci,caused_by"),
        "sysparm_limit":  10000,
        "sysparm_display_value": "false",
    })
    print(f" {len(records)} found")

    incidents = []
    for r in records:
        resolved = r.get("resolved_at") or r.get("closed_at")
        cat      = r.get("category","")
        subcat   = r.get("subcategory","")
        full_cat = f"{cat}/{subcat}" if subcat else cat

        caused_by = r.get("caused_by","")
        change_request_id = None
        if caused_by and isinstance(caused_by, dict):
            change_request_id = caused_by.get("value")
        elif caused_by and str(caused_by).startswith("CHG"):
            change_request_id = caused_by

        ag = r.get("assignment_group","")
        labels = []
        if ag and isinstance(ag, dict): labels.append(ag.get("display_value",""))
        elif ag: labels.append(str(ag))

        incidents.append({
            "issue_id":              r.get("number", r.get("sys_id")),
            "title":                 (r.get("short_description","") or "")[:500],
            "description":           (r.get("description","") or "")[:2000],
            "type":                  "INCIDENT",
            "severity":              PRIORITY_MAP.get(str(r.get("priority","3")),"P3"),
            "status":                STATE_MAP.get(str(r.get("state","1")),"OPEN"),
            "category":              full_cat,
            "labels":                [l for l in labels if l],
            "created_at":            sn_ts(r.get("sys_created_on")) or "",
            "resolved_at":           sn_ts(resolved),
            "change_request_id":     change_request_id,
            "related_deployment_id": None,
            "service_affected":      r.get("cmdb_ci",""),
            "assignee":              r.get("assigned_to",""),
        })

    out = {
        "meta": {"project_name": a.project, "source_tool": "servicenow",
                 "collected_at": datetime.now(timezone.utc).isoformat(),
                 "schema_version": "1.0"},
        "incidents": incidents,
    }
    with open(a.output, "w") as f:
        json.dump(out, f, indent=2)

    resolved  = sum(1 for i in incidents if i["status"]=="RESOLVED")
    with_cr   = sum(1 for i in incidents if i.get("change_request_id"))
    with_cat  = sum(1 for i in incidents if i.get("category"))

    print(f"\n✓  {len(incidents)} incidents  ({resolved} resolved)")
    print(f"   {with_cr} linked to change requests  ← strong DORA signal")
    print(f"   {with_cat} have ITSM category          ← classification signal")
    print(f"✓  Saved to {a.output}")
    print(f"\n→  Upload {a.output} to the DORA portal\n")


if __name__ == "__main__":
    main()
