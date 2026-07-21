/**
 * compute-disk IT service — drawer shell only.
 * List + insight canvas live in frontend/src/disks/.
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
  getDiskPropertyValue,
  formatDiskAssessmentPropertyValue,
  buildDiskPropertiesSections,
  diskDrawerSectionsToPropertyGroups,
  normalizeDiskProperties,
} from './utils/diskUtils';

export { default as DiskPropertiesPanel } from './components/DiskPropertiesPanel';
