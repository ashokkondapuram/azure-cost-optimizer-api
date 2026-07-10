/**
 * Provisioned IOPS/throughput from Disks - Get ARM properties and Azure tier tables.
 * @see https://learn.microsoft.com/en-us/rest/api/compute/disks/get?view=rest-compute-2026-03-02
 */

import tierSpecData from '../data/disk_tier_specs.json';

const TIER_SPECS = tierSpecData.disk_tier_specs || {};
const PERFORMANCE_TIER_LIMITS = tierSpecData.performance_tier_limits || {};

function tierSpecForSku(skuName) {
  const sku = String(skuName || '').trim();
  if (!sku) return null;
  if (TIER_SPECS[sku]) return TIER_SPECS[sku];
  if (sku === 'Premium_ZRS' && TIER_SPECS.Premium_LRS) return TIER_SPECS.Premium_LRS;
  if (sku === 'StandardSSD_ZRS' && TIER_SPECS.StandardSSD_LRS) return TIER_SPECS.StandardSSD_LRS;
  return null;
}

export function provisionedLimitsFromPerformanceTier(performanceTier) {
  const tier = String(performanceTier || '').trim().toUpperCase();
  if (!tier) return { iops: null, mbps: null };
  const limits = PERFORMANCE_TIER_LIMITS[tier];
  if (!limits) return { iops: null, mbps: null };
  return {
    iops: limits.iops != null ? Number(limits.iops) : null,
    mbps: limits.mbps != null ? Number(limits.mbps) : null,
  };
}

export function provisionedLimitsFromTier(skuName, sizeGb) {
  const spec = tierSpecForSku(skuName);
  if (!spec) return { iops: null, mbps: null };

  const size = Number(sizeGb) || 0;
  const sizeRanges = spec.size_ranges || [];
  if (size > 0 && sizeRanges.length) {
    for (const band of sizeRanges) {
      const minGb = Number(band.min_gb) || 0;
      const maxGb = band.max_gb == null ? null : Number(band.max_gb);
      if (size < minGb) continue;
      if (maxGb == null || size <= maxGb) {
        return {
          iops: band.iops != null ? Number(band.iops) : null,
          mbps: band.mbps != null ? Number(band.mbps) : null,
        };
      }
    }
  }

  return {
    iops: spec.default_iops != null ? Number(spec.default_iops) : null,
    mbps: spec.default_mbps != null ? Number(spec.default_mbps) : null,
  };
}

export function resolveDiskProvisionedPerformance(resource) {
  const props = resource?.properties || {};
  const skuName = resource?.sku?.name || props.sku || '';
  const sizeGb = props.diskSizeGB ?? props.DiskSizeGB ?? 0;
  const performanceTier = props.tier ?? props.Tier;

  const armIops = props.diskIOPSReadWrite ?? props.DiskIOPSReadWrite;
  const armMbps = props.diskMBpsReadWrite ?? props.DiskMBpsReadWrite;

  let tier = provisionedLimitsFromPerformanceTier(performanceTier);
  if (tier.iops == null && tier.mbps == null) {
    tier = provisionedLimitsFromTier(skuName, sizeGb);
  }

  const iops = armIops != null && armIops !== '' ? armIops : tier.iops;
  const mbps = armMbps != null && armMbps !== '' ? armMbps : tier.mbps;

  return { iops, mbps };
}
