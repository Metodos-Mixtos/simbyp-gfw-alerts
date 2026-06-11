# Database Integration for GFW Alerts - Cloud Run Deployment Guide

## Overview

The GFW alerts pipeline now logs alert statistics and generated reports to PostgreSQL (Cloud SQL). This guide explains how to configure the application for both local development and Cloud Run deployment.

## Local Development Setup

### Prerequisites
- Cloud SQL Proxy running (connects to Cloud SQL via Unix socket)
- `.env` file configured with `DATABASE_URL`

### 1. Start Cloud SQL Proxy (if not already running)

```bash
export GOOGLE_APPLICATION_CREDENTIALS='/Users/Daniel/Desktop/keys/service-account-bosques.json'
cloud_sql_proxy -instances=bosques-bogota-416214:us-central1:simbyp-users-db -unix_socket_path=/tmp/cloudsql
```

### 2. Verify .env Configuration

Your `.env` file should contain:

```
DATABASE_URL=postgresql://simbyp_app:jimmyz-redka6-xuHduv@/simbyp_db?host=/tmp/cloudsql/bosques-bogota-416214:us-central1:simbyp-users-db
```

### 3. Run the Pipeline

```bash
cd /Users/Daniel/Desktop/code/simbyp-gfw-alerts
python gfw_alerts/main.py
```

The application will automatically:
- Initialize database tables on first run
- Log alert statistics after processing
- Log report metadata after generation

## Cloud Run Deployment

### 1. Set Environment Variables

Deploy to Cloud Run with the DATABASE_URL environment variable:

```bash
gcloud run deploy simbyp-gfw-alerts \
  --source . \
  --region us-central1 \
  --set-env-vars DATABASE_URL="postgresql://simbyp_app:PASSWORD@/simbyp_db?host=/cloudsql/bosques-bogota-416214:us-central1:simbyp-users-db" \
  --service-account=sa-bosques-app@bosques-bogota-416214.iam.gserviceaccount.com \
  --memory=2Gi \
  --timeout=3600
```

**Or** use Secret Manager for the password:

```bash
gcloud run deploy simbyp-gfw-alerts \
  --source . \
  --region us-central1 \
  --set-secrets DATABASE_URL=DB_CONNECTION_URL:latest \
  --service-account=sa-bosques-app@bosques-bogota-416214.iam.gserviceaccount.com \
  --memory=2Gi \
  --timeout=3600
```

### 2. Cloud Run Configuration

- **Pool Strategy**: Automatically uses `NullPool` on Cloud Run (detected via `K_SERVICE` env var)
- **Connection Pattern**: Unix socket connections work on Cloud Run with Cloud SQL connector
- **Stateless**: Each invocation creates fresh connections; no session persistence

### 3. IAM Requirements

Service account `sa-bosques-app@bosques-bogota-416214.iam.gserviceaccount.com` needs:
- `Cloud SQL Client` role (to connect to Cloud SQL)
- `Secret Accessor` role (if using Secret Manager for DATABASE_URL)

## Database Schema

### Tables Created

#### `alert_statistics`
Stores daily alert statistics aggregated by type, source, and location.

- `id` (UUID, PK)
- `date` (DATE)
- `alert_type` (VARCHAR): weekly_alerts, monthly_built_area, trimestral_alerts
- `alert_source` (VARCHAR): gfw, psa, urban_sprawl
- `alert_count` (INTEGER)
- `municipality_code` (VARCHAR): Optional Colombian DIVIPOLA code
- `metadata` (JSONB): Additional metrics (summary, clusters count, etc.)
- `created_at` (TIMESTAMP)

#### `reports_sent`
Tracks generated reports and their delivery status.

- `id` (UUID, PK)
- `alert_type` (VARCHAR): weekly_alerts, monthly_built_area, trimestral_alerts
- `report_title` (VARCHAR)
- `report_url` (VARCHAR): GCS path
- `report_date` (DATE): Date the report covers
- `sent_at` (TIMESTAMP)
- `recipient_count` (INTEGER)
- `status` (VARCHAR): generated, sent, failed, partial
- `error_message` (VARCHAR)
- `metadata` (JSONB): Output folder, alert counts, clusters info

## Integration Points

### 1. Alert Processing
After alerts are processed and enriched with geographic data, statistics are logged:

```python
log_alert_statistics(
    alert_date=alert_date,
    alert_type='weekly_alerts',
    alert_source='gfw',
    alert_count=len(gfw_alerts),
    metadata={...}
)
```

### 2. Report Generation
After the HTML report is rendered and uploaded to GCS:

```python
log_report_sent(
    alert_type='weekly_alerts',
    report_title='Alertas GFW - Semana 2026-06-02 a 2026-06-08',
    report_url='gs://reportes-simbyp/reportes_gfw/...',
    status='generated',
    metadata={...}
)
```

## Graceful Degradation

If DATABASE_URL is not set:
- Database logging is skipped
- Pipeline continues normally
- GCS uploads proceed as usual
- Warnings printed to logs

This allows the pipeline to work independently of the database.

## Troubleshooting

### "Database connection timeout"
- Check Cloud SQL Proxy is running (local dev)
- Verify service account has `Cloud SQL Client` role (Cloud Run)
- Check DATABASE_URL format and credentials

### "Table already exists" 
- Safe to ignore; tables only created if they don't exist
- Application will continue normally

### "No database connection"
- Verify DATABASE_URL is set in environment
- Check Cloud SQL instance is running
- Review application logs for connection errors

## Verification

Query the database to verify logging is working:

```sql
-- Check alert statistics
SELECT COUNT(*), alert_type, alert_source 
FROM alert_statistics 
GROUP BY alert_type, alert_source;

-- Check reports
SELECT alert_type, status, COUNT(*) 
FROM reports_sent 
GROUP BY alert_type, status;
```

Or via the Toolbox MCP (if configured):

```python
import subprocess
result = subprocess.run([
    '/Users/Daniel/tools/toolboox/toolbox', 
    '--prebuilt', 'cloud-sql-postgres',
    '--stdio'
], capture_output=True, text=True)
```
