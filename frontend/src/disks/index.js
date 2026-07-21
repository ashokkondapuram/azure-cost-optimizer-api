/** Managed disks module — concept v2 + disk-assessment.json */

export { default as DiskInventoryPage } from './DiskInventoryPage';
export { default as DiskInsightCanvas } from './DiskInsightCanvas';

export * from './diskAssessment';
export * from './diskList';
export * from './diskApiModel';
export * from './diskInsight';

export function isDiskCanonicalType(type) {
  const t = String(type || '').toLowerCase();
  return t === 'compute/disk' || t.includes('microsoft.compute/disks');
}
