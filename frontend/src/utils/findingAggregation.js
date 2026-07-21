/** Expand aggregated API findings into per-rule rows for resource indexes. */

export function expandFindingRecommendations(finding) {
  if (!finding || typeof finding !== 'object') return [];
  if (finding.aggregated) {
    const children = finding.recommendations || finding.child_findings;
    if (Array.isArray(children) && children.length) {
      return children.map((child) => ({
        ...child,
        resource_id: child.resource_id || finding.resource_id,
        resource_name: child.resource_name || finding.resource_name,
        resource_type: child.resource_type || finding.resource_type,
        resource_group: child.resource_group || finding.resource_group,
        location: child.location || finding.location,
        subscription_id: child.subscription_id || finding.subscription_id,
        status: child.status || finding.status,
      }));
    }
  }
  return [finding];
}

export function recommendationCountForFinding(finding) {
  if (!finding || typeof finding !== 'object') return 0;
  if (finding.aggregated) {
    const count = Number(finding.recommendation_count);
    if (Number.isFinite(count) && count > 0) return count;
    const children = finding.recommendations || finding.child_findings;
    if (Array.isArray(children)) return children.length;
  }
  return 1;
}

export function aggregatedRecommendationHeadline(finding, headline) {
  const count = recommendationCountForFinding(finding);
  if (count <= 1) return headline;
  return `${headline} · ${count} recommendations`;
}
