# Security

## Application authentication

The SPA uses **local username/password** accounts stored in PostgreSQL (`app_users` table), not Azure AD SSO.

- **Login:** `POST /auth/login` returns a JWT access token.
- **Sessions:** Bearer token in `Authorization` header; validated on protected API routes via `AppAuthMiddleware`.
- **Roles:** `admin` (sync, analyze, settings, live Azure reads) and `viewer` (read scoped data).
- **Rate limiting:** Failed login attempts are tracked in the database (`login_attempts` table) per client IP.
- **Token validity:** Middleware verifies the user still exists and `is_active=true` on each request.
- **Production gates:** Startup validation requires `JWT_SECRET`, `SETTINGS_ENCRYPTION_KEY`, `K8S_AGENT_TOKEN`, `ADMIN_PASSWORD`, PostgreSQL, and `AUTH_ENABLED=true`.

### Client-side note

The React app stores JWTs in `localStorage` today. For hardened production deployments, prefer httpOnly cookies or a backend-for-frontend pattern to reduce XSS token theft risk.

## API authorization

Protected route roots include `/costs`, `/resources`, `/optimize`, `/dashboard`, `/settings`, `/metrics`, `/admin`, `/sync`, `/advisor`, `/alerts`, `/outliers`, and `/budgets`.

- **Subscription scoping:** Data endpoints call `ensure_subscription_known()` — subscriptions must appear in the catalog or synced inventory.
- **Admin gates:** `require_admin_user()` on sync, analyze, cost sync, settings, engine config, and live Azure/Monitor calls.

## Kubernetes agent

- Routes under `/k8s/*` skip JWT but require `X-API-Key`.
- When `AUTH_ENABLED=true`, an agent token must be configured or requests are rejected.

## Azure access

The app uses Managed Identity or configured service principal credentials (Settings → Azure) for ARM and Cost Management APIs.

Minimum Azure RBAC on each subscription:

- **Cost Management Reader** — cost export and live cost queries
- **Reader** — resource inventory

Store secrets in Azure App Service application settings or Key Vault references — never commit credentials to source control.

## Related docs

- [api-reference.md](./api-reference.md)
- [DEPLOY_APP_SERVICE.md](./DEPLOY_APP_SERVICE.md)
- [AZURE_PERMISSIONS.md](./AZURE_PERMISSIONS.md)
