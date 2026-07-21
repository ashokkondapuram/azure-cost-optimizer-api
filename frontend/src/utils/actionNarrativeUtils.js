/** Resolve concrete narrative and evidence highlights for proposed actions. */

import { parseActionAnalysis } from './actionAnalysisUtils';
import { evidenceOptimizationMetrics } from './evidenceUtils';
import { toDisplayText } from './formatDisplay';

function parseJsonField(value, fallback) {
  if (value == null) return fallback;
  if (typeof value === 'object') return value;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function dedupeHighlights(items) {
  const seen = new Set();
  const out = [];
  for (const item of items || []) {
    const label = toDisplayText(item?.label);
    const value = toDisplayText(item?.value);
    if (!label || !value) continue;
    const key = `${label.toLowerCase()}:${value.toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ label, value });
  }
  return out;
}

/** Evidence metric highlights for a proposed optimization action. */
export function resolveActionEvidenceHighlights(action, findings = []) {
  const analysis = parseActionAnalysis(action);
  const util = analysis?.utilization || {};
  const fromAction = dedupeHighlights(util.narrative_highlights);

  if (fromAction.length) return fromAction.slice(0, 8);

  const metrics = evidenceOptimizationMetrics({ optimization_metrics: util.optimization_metrics });
  const fromMetrics = dedupeHighlights(
    (metrics?.performance || []).map((m) => ({
      label: m.label || m.id,
      value: m.formatted || (m.value != null ? String(m.value) : ''),
    })),
  );
  if (fromMetrics.length) return fromMetrics.slice(0, 8);

  const fromFindings = dedupeHighlights(
    (findings || []).flatMap((f) => f.narrative_highlights || []),
  );
  return fromFindings.slice(0, 8);
}

/** Best available narrative text for a proposed action (prefers evidence-backed reason). */
export function resolveActionNarrative(action, findings = []) {
  const reason = toDisplayText(action?.action_reason);
  if (reason && reason !== '—' && reason.length > 40) return reason;

  const linkedFinding = (findings || []).find((f) => {
    const n = f.narrative || f.evidence?.summary;
    return n && toDisplayText(n) !== '—';
  });
  if (linkedFinding?.narrative && toDisplayText(linkedFinding.narrative) !== '—') {
    return linkedFinding.narrative;
  }
  if (linkedFinding?.evidence?.summary) return linkedFinding.evidence.summary;

  return reason !== '—' ? reason : '';
}

/** Preview text for recommendation tiles — prefers evidence summary over generic copy. */
export function resolveFindingPreviewText(finding) {
  if (finding?.narrative && toDisplayText(finding.narrative) !== '—') {
    return finding.narrative;
  }

  const summary = finding?.evidence?.summary;
  if (summary && toDisplayText(summary) !== '—') return summary;

  const highlights = finding?.narrative_highlights || [];
  if (highlights.length >= 2) {
    return highlights
      .slice(0, 3)
      .map((h) => `${h.label}: ${h.value}`)
      .join(' · ');
  }

  const fallback = finding?.recommendation || finding?.detail;
  return fallback && toDisplayText(fallback) !== '—' ? fallback : '';
}
