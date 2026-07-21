/** Cost trigger / signal helpers for findings and table badges. */

function parseEvidence(finding) {
  if (!finding) return {};
  if (typeof finding.evidence === 'string') {
    try {
      return JSON.parse(finding.evidence);
    } catch {
      return {};
    }
  }
  return finding.evidence && typeof finding.evidence === 'object' ? finding.evidence : {};
}

export function findingTriggerMetrics(finding) {
  if (Array.isArray(finding?.trigger_metrics) && finding.trigger_metrics.length) {
    return finding.trigger_metrics;
  }
  const evidence = parseEvidence(finding);
  return Array.isArray(evidence.trigger_metrics) ? evidence.trigger_metrics : [];
}

export function countTriggerMetricsForFindings(findings = []) {
  const keys = new Set();
  for (const finding of findings) {
    for (const item of findingTriggerMetrics(finding)) {
      const key = item?.fact_key || item?.label;
      if (key) keys.add(key);
    }
  }
  return keys.size;
}

export function primaryTriggerLabel(findings = []) {
  for (const finding of findings) {
    const metrics = findingTriggerMetrics(finding);
    if (metrics.length) {
      return metrics[0].label || metrics[0].fact_key || null;
    }
  }
  return null;
}
