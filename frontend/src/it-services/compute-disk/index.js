/**
 * compute-disk IT service — frontend public API.
 * Owned code lives in this folder; see it-services/compute-disk/manifest.yaml
 */

import './styles/disk-drawer.css';

export {
  SERVICE_ID,
  API_PATH,
  CANONICAL_TYPE,
  matchesResource,
  PropertiesPanel,
  enrichInventoryContext,
  hideStateKpi,
  skipOverviewTiles,
  collapseMetricsSection,
  costDriversDefaultOpen,
} from './drawer';

export { enrichEvidenceFilter } from './evidence';

export {
  isDiskResource,
  diskSku,
  diskStateLabel,
  diskLastOwnershipUpdate,
  getDiskPropertyTiles,
  getDiskDrawerSections,
  getDiskHostAttachment,
  diskAttachmentSummary,
  diskAttachmentTypeLabel,
  diskProvisionedIopsLabel,
  diskProvisionedMbpsLabel,
  diskSizeGbLabel,
} from './utils/diskUtils';

export { default as DiskPropertiesPanel } from './components/DiskPropertiesPanel';
