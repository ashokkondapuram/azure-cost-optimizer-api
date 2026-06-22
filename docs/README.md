# Documentation Index

This directory contains detailed documentation for the Azure Cost Optimizer Platform.

## Documents

### architecture.md
Complete architecture description, logical components, runtime interactions, and scaling considerations.

### backend.md
Detailed backend explanation including modules, responsibilities, request lifecycle, persistence behavior, and extension model.

### frontend.md
Detailed frontend explanation including routes, components, user flow, state handling, API integration, and UI hardening recommendations.

### api-reference.md
Detailed endpoint-by-endpoint API contract documentation including method, parameters, behavior, expected responses, and operational notes.

### database.md
Schema-level documentation for PostgreSQL tables, expected data flow, retention guidance, indexing strategy, and future data model improvements.

### security.md
Managed Identity, least privilege RBAC, application-layer security expectations, secrets guidance, network hardening, and compliance-focused recommendations.

### kubernetes-agent.md
Explains the lightweight Kubernetes collector, required RBAC, metrics-server dependency, poll cycle, resource footprint, and production considerations.

### operations.md
Runbook-oriented guidance for monitoring, logging, health checks, incident handling, backups, maintenance, and change management.

### deployment-manual.md
Step-by-step manual deployment guide for environments where infrastructure is created outside this repository.

### production-readiness.md
Enterprise-grade hardening checklist and gap analysis guide for selling or deploying the platform to large enterprises.

## Suggested order
1. architecture.md
2. backend.md
3. frontend.md
4. api-reference.md
5. security.md
6. operations.md
7. production-readiness.md
