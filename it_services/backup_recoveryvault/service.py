"""IT service entity — public exports for Recovery Services vault."""

from __future__ import annotations

SERVICE_ID = "backup-recoveryvault"
CANONICAL_TYPE = "backup/recoveryvault"
ARM_TYPE = "Microsoft.RecoveryServices/vaults"
DISPLAY_NAME = "Recovery Services vault"
API_SLUG = "recoveryvault"
COMPONENT = "Backup"

from it_services.backup_recoveryvault.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.backup_recoveryvault.engine.sub_engine import BackupSubEngine as SubEngine

