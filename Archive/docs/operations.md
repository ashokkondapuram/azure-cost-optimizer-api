# Operations

## Monitoring
Track at minimum:
- backend availability,
- backend latency,
- backend error rate,
- Azure API failure rate,
- database connectivity,
- database storage growth,
- Kubernetes ingestion success rate.

## Logging
Adopt structured JSON logs with correlation IDs. Send logs to a central platform and define retention and search standards.

## Health checks
The current `/health` endpoint is suitable only as a basic liveness probe. In enterprise production, add:
- readiness endpoint,
- dependency check endpoint,
- degraded mode signaling.

## Incident handling
Define runbooks for:
- Azure permission failures,
- PostgreSQL connectivity failures,
- Kubernetes ingestion failures,
- increased API latency,
- unexpected cost query failures.

## Data retention
Decide retention windows for:
- raw cost payloads,
- historical cost records,
- Kubernetes utilization snapshots,
- application logs,
- audit evidence.

## Release management
Implement:
- pull request reviews,
- static analysis,
- dependency scanning,
- test gates,
- version tagging,
- rollback procedures.
