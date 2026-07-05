# Manual Deployment Guide

This guide assumes that Azure Web App and PostgreSQL are created manually outside this repository.

## 1. Prepare PostgreSQL
Create a PostgreSQL database and collect the connection string.

Expected environment variable format:
```text
postgresql+psycopg2://<user>:<password>@<host>:5432/<database>
```

## 2. Configure backend application settings
Set the following environment variables in the Azure Web App:
- `DATABASE_URL` (or `POSTGRESQLCONNSTR_<name>`)
- `AZURE_AUTH_MODE=managed_identity`
- `AZURE_DEFAULT_SUBSCRIPTION_ID=<subscription-guid>`
- `SETTINGS_ENCRYPTION_KEY=<fernet-key>`
- `APP_ENV=production`
- `LOG_LEVEL=INFO`
- `REQUEST_TIMEOUT_SECONDS=60`
- `CORS_ALLOWED_ORIGINS=https://<frontend-domain>`

Startup command:
```text
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

See [DEPLOY_APP_SERVICE.md](./DEPLOY_APP_SERVICE.md) for the full managed-identity deployment guide.

## 3. Enable Managed Identity
Turn on system-assigned or user-assigned Managed Identity for the backend host.

## 4. Assign Azure RBAC
Grant:
- `Cost Management Reader`
- `Reader`

Use the narrowest scope that satisfies the business requirement.

## 5. Deploy backend code
Deploy the backend code to the Web App using your chosen method, such as:
- zip deployment,
- GitHub Actions,
- Azure DevOps pipeline,
- container deployment.

## 6. Deploy frontend
The frontend can be deployed separately to Static Web Apps, another Web App, or any enterprise-approved hosting platform.

Set:
```text
REACT_APP_API_URL=https://<backend-domain>
```

Then build and publish:
```bash
cd frontend
npm install
npm run build
```

## 7. Deploy Kubernetes agent
Update the backend ingestion URL in the manifest and apply the files to the cluster.

## 8. Validate
Validate the following:
- `/health` returns success,
- cost query works,
- resource inventory works,
- PostgreSQL receives records,
- Kubernetes telemetry appears in the UI,
- browser CORS policy works correctly.
