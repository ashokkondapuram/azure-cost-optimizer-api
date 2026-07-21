# Platform auth

Authentication, session management, admin settings, and Kubernetes agent endpoints. Internal service id: `platform-core`.

- **Port:** 8010
- **Routes:** `/auth`, `/settings`, `/admin`, `/k8s`

## Run

```bash
uvicorn services.platform-auth.src.main:app --host 127.0.0.1 --port 8010
```

## Parent

[services/](../README.md)
