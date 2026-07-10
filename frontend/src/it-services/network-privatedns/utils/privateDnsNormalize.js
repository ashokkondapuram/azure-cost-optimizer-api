/** Private DNS zone row enrichment — zones use record sets + type, not ARM sku. */

import { toDisplayText } from '../../../utils/formatDisplay';

export function formatPrivateDnsZoneSummary(props) {
  if (!props) return '';
  const count = props.numberOfRecordSets;
  let recordPart = '';
  if (count != null && count !== '') {
    const n = Number(count);
    if (!Number.isNaN(n)) {
      recordPart = `${n} record set${n === 1 ? '' : 's'}`;
    }
  }
  const zoneType = props.zoneType;
  if (recordPart && zoneType) return `${recordPart} · ${zoneType}`;
  return recordPart || zoneType || '';
}

export function enrichPrivateDnsRow(row) {
  const props = row?.properties || {};
  const summary = formatPrivateDnsZoneSummary(props);
  const recordSetCount = props.numberOfRecordSets != null ? Number(props.numberOfRecordSets) : null;
  return {
    ...row,
    sku: summary || row.sku || '',
    recordSetCount: Number.isNaN(recordSetCount) ? row.recordSetCount : recordSetCount,
    dnsZoneSummary: summary || row.dnsZoneSummary,
  };
}

export function privateDnsDisplaySummary(row) {
  const enriched = enrichPrivateDnsRow(row);
  const text = enriched.dnsZoneSummary || enriched.sku;
  return toDisplayText(text);
}
