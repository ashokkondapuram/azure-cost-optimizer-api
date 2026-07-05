/** Azure Monitor supported-metrics documentation URLs. */

const AZURE_METRICS_DOC_BASE =
  'https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics';

export function azureMetricsDocUrl(docRef) {
  const ref = String(docRef || '').trim();
  if (!ref) return null;
  if (ref.startsWith('http://') || ref.startsWith('https://')) return ref;
  const slug = ref.endsWith('-metrics') ? ref : `${ref}-metrics`;
  return `${AZURE_METRICS_DOC_BASE}/${slug}`;
}
