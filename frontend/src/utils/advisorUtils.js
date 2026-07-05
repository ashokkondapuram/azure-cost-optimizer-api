/** Azure Advisor recommendation display helpers. */

export const ADVISOR_INDEX_LIMIT = 500;
export const ADVISOR_INDEX_MAX = 5000;

/** Fetch all stored advisor pages (API caps each page at 500). */
export async function fetchAllAzureAdvisorRecommendations(fetchPage, subscription) {
  const limit = ADVISOR_INDEX_LIMIT;
  let offset = 0;
  let allItems = [];
  let total = 0;

  while (offset < ADVISOR_INDEX_MAX) {
    const page = await fetchPage({
      subscription_id: subscription,
      status: 'Active',
      limit,
      offset,
    });
    const batch = page?.items || [];
    allItems = allItems.concat(batch);
    total = page?.total ?? allItems.length;
    offset += limit;
    if (!batch.length || allItems.length >= total) break;
  }

  return {
    items: allItems,
    total,
    count: allItems.length,
    source: 'azure_advisor',
  };
}

const CATEGORY_LABELS = {
  Cost: 'Cost',
  Performance: 'Performance',
  HighAvailability: 'Reliability',
  Security: 'Security',
  OperationalExcellence: 'Operational excellence',
};

const IMPACT_TONES = {
  High: 'high',
  Medium: 'medium',
  Low: 'low',
};

export function advisorCategoryLabel(category) {
  if (!category) return 'Advisor';
  return CATEGORY_LABELS[category] || String(category).replace(/([a-z])([A-Z])/g, '$1 $2');
}

export function advisorImpactTone(impact) {
  return IMPACT_TONES[impact] || 'muted';
}

export function normalizeAdvisorResourceId(resourceId) {
  return String(resourceId || '').trim().toLowerCase().replace(/\/+$/, '');
}

export function advisorMonthlySavings(rec) {
  return rec?.potential_savings_monthly ?? rec?.potentialSavingsMonthly ?? null;
}

export function advisorSavingsLabel(amount, currency = 'USD') {
  if (amount == null || Number.isNaN(Number(amount)) || Number(amount) <= 0) return null;
  const value = Number(amount);
  const prefix = currency === 'USD' ? '$' : `${currency} `;
  return `${prefix}${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}/mo`;
}

/** Pick the highest-impact recommendation for compact table display. */
export function primaryAdvisorRecommendation(recommendations = []) {
  if (!recommendations?.length) return null;
  const impactRank = { High: 0, Medium: 1, Low: 2 };
  return [...recommendations].sort((a, b) => {
    const ia = impactRank[a.impact] ?? 3;
    const ib = impactRank[b.impact] ?? 3;
    if (ia !== ib) return ia - ib;
    return (advisorMonthlySavings(b) || 0) - (advisorMonthlySavings(a) || 0);
  })[0];
}

export function indexAdvisorByResourceId(items = []) {
  const map = new Map();
  for (const item of items) {
    const key = normalizeAdvisorResourceId(item.resource_id);
    if (!key) continue;
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(item);
  }
  return map;
}
