# Security

## Identity model
The backend is designed to authenticate to Azure APIs using Managed Identity. This removes the need to store Azure client secrets in the codebase.

## Required Azure RBAC
- `Cost Management Reader` for cost data.
- `Reader` for Azure resource inventory.

Scope these roles as narrowly as your operating model allows.

## Application security posture
The sample code is a functional baseline, not a completed enterprise security implementation. Before production rollout, implement:
- frontend authentication,
- backend authentication,
- backend authorization,
- secure CORS policy,
- rate limiting,
- audit logging,
- request tracing,
- tamper-resistant log storage,
- secret rotation model,
- vulnerability scanning.

## Secrets handling
- Do not hardcode database credentials.
- Use Azure Web App settings and preferably Key Vault references.
- Never log bearer tokens.
- Never expose internal operational errors directly to end users in production.

## Network security
- Restrict backend ingress.
- Restrict PostgreSQL access to approved sources.
- Consider private endpoints and VNet integration.
- Place the frontend behind enterprise identity and WAF controls.

## Kubernetes security
The collector pod runs with read-only RBAC for nodes, pods, and metrics APIs. Keep the service account dedicated to this component and avoid sharing it with other workloads.

## Compliance posture
For top-tier enterprise customers, align implementation and evidence generation with the organization's required controls, for example:
- access reviews,
- change control,
- secure SDLC,
- audit evidence retention,
- incident response procedures,
- backup and disaster recovery tests.
