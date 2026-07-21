"""IT service entity — public exports for Key vault."""

from __future__ import annotations

SERVICE_ID = "security-keyvault"
CANONICAL_TYPE = "security/keyvault"
ARM_TYPE = "Microsoft.KeyVault/vaults"
DISPLAY_NAME = "Key vault"
API_SLUG = "keyvaults"
COMPONENT = "Key Vault"

from it_services.security_keyvault.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.security_keyvault.engine.sub_engine import KeyVaultSubEngine as SubEngine

