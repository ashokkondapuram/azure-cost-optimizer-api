-- Raise connection limit for multi-service local Docker (6 platform services + workers).
-- Primary tuning is via postgres command in docker-compose; this documents the target.
-- Verify after deploy: SHOW max_connections;

-- Note: max_connections must be set at server start (docker command -c max_connections=...).
-- This file is informational for operators using custom postgresql.conf mounts.
