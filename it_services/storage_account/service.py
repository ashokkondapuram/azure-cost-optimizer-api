"""IT service entity — public exports for Storage account."""

from __future__ import annotations

SERVICE_ID = "storage-account"
CANONICAL_TYPE = "storage/account"
ARM_TYPE = "Microsoft.Storage/storageAccounts"
DISPLAY_NAME = "Storage account"
API_SLUG = "storage"
COMPONENT = "Storage Accounts"

from it_services.storage_account.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.storage_account.engine.sub_engine import StorageSubEngine as SubEngine

