# DORA Platform — Deployment Guide

## Prerequisites
- Docker + Docker Compose installed
- Git
- 4GB RAM minimum

---

## Step 1 — Clone and configure

```bash
git clone <your-repo> dora-platform
cd dora-platform

cp .env.example .env
```

Edit `.env`:
```
MYSQL_PASSWORD=choose_a_strong_password
MYSQL_DATABASE=dora_platform
SECRET_KEY=generate_32_random_chars
```

Generate a secret key:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Step 2 — Start the stack

```bash
docker-compose up -d
```

This starts:
- MySQL 8.0 on port 3306 (schema auto-applied)
- FastAPI backend on port 8000
- React frontend on port 3000

Check everything is running:
```bash
docker-compose ps
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok","db":"connected"}`

---

## Step 3 — Open the portal

http://localhost:3000

---

## Step 4 — Collect your first data

### GitHub (SCM)
```bash
pip install requests
python scripts/collectors/collect_github.py \
  --token ghp_YOUR_TOKEN \
  --repo your-org/your-repo \
  --project payments-service \
  --days 180
```
Outputs: `scm_data.json`

### Jenkins (CI/CD)
```bash
python scripts/collectors/collect_jenkins.py \
  --url https://jenkins.company.com \
  --user your-user \
  --token YOUR_API_TOKEN \
  --job deploy-production \
  --project payments-service \
  --days 180
```
Outputs: `cicd_data.json`

### ServiceNow (Incidents)
```bash
python scripts/collectors/collect_servicenow.py \
  --instance company.service-now.com \
  --user api_user \
  --password secret \
  --project payments-service \
  --days 180 \
  --priority 1,2
```
Outputs: `incidents_data.json`

---

## Step 5 — Upload via portal OR API

### Via portal (recommended)
1. Open http://localhost:3000
2. Enter project name
3. Upload JSON files
4. View DORA dashboard

### Via API directly
```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@scm_data.json"

curl -X POST http://localhost:8000/api/upload \
  -F "file=@cicd_data.json"

curl -X POST http://localhost:8000/api/upload \
  -F "file=@incidents_data.json"
```

---

## Step 6 — View metrics

```bash
# Current DORA bands
curl http://localhost:8000/api/projects/payments-service/dora | python3 -m json.tool

# 90-day trends
curl http://localhost:8000/api/projects/payments-service/trends

# Incidents needing review
curl "http://localhost:8000/api/projects/payments-service/incidents?needs_review=true"
```

---

## Step 7 — Review flagged incidents

Any incident the classifier is uncertain about (<40% confidence) is flagged.

```bash
# See flagged incidents
curl "http://localhost:8000/api/projects/YOUR_PROJECT/incidents?needs_review=true"

# Reclassify incident id=42
curl -X POST http://localhost:8000/api/incidents/42/reclassify \
  -H "Content-Type: application/json" \
  -d '{"classification":"DEPLOYMENT_FAILURE","reviewer":"your-name","notes":"Caused by bad deploy"}'
```

---

## API Reference (key endpoints)

| Method | Path | Description |
|--------|------|-------------|
| GET  | /api/health | Health check |
| GET  | /api/projects | List all projects |
| GET  | /api/projects/{id} | Project summary + record counts |
| POST | /api/upload | Upload scm/cicd/itsm JSON |
| GET  | /api/projects/{id}/dora | Current DORA metrics |
| GET  | /api/projects/{id}/trends | 90-day daily trend data |
| GET  | /api/projects/{id}/incidents | Incident list with classification |
| POST | /api/projects/{id}/recompute | Force recompute dora_daily |
| POST | /api/incidents/{id}/reclassify | Human override classification |
| GET  | /api/scripts/{tool} | Download collection script |

Full interactive docs: http://localhost:8000/docs

---

## Run Tests

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests/test_all.py -v
```

---

## Troubleshooting

**Backend can't connect to MySQL:**
```bash
docker-compose logs mysql
# Wait for: "ready for connections"
docker-compose restart backend
```

**Schema not applied:**
```bash
docker-compose down -v   # wipes DB volume
docker-compose up -d     # re-applies schema
```

**Metrics showing as insufficient_data:**
- Need deployments AND pull_requests with matching commit_sha for Lead Time
- Need incidents with cfr_include=1 for CFR/MTTR
- Upload all 3 data types before expecting all 4 metrics

**Incidents all showing as OTHER:**
- Run the enhanced ServiceNow script — it captures category and change_request_id
- These are the strongest classifier signals
- Or manually reclassify via API

---

## Production deployment notes

1. Change all passwords in `.env`
2. Set `CORS_ORIGINS` to your specific frontend domain
3. Add TLS via nginx reverse proxy
4. Mount a persistent backup for the mysql volume
5. Set up a nightly cron to recompute all projects:

```bash
curl -X POST http://localhost:8000/api/projects/YOUR_PROJECT/recompute
```
