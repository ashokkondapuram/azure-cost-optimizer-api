import catalog from './rulesCatalog.json';

export const STATIC_COMPONENTS = catalog.components;
export const STATIC_RULES = catalog.rules;

const COMPONENT_ORDER = [
  'Virtual Machines', 'Managed Disks', 'App Service', 'AKS',
  'Storage Accounts', 'Public IPs', 'Network Interfaces', 'NAT Gateways',
  'Load Balancers', 'Application Gateways',
  'SQL Database', 'Cosmos DB', 'Redis Cache',
  'Key Vault', 'Budgets', 'Commitments', 'Governance',
];

/** Group a flat rules array by component (API fallback). */
export function groupRulesByComponent(rules) {
  const map = {};
  (rules || []).forEach(rule => {
    const comp = rule.component || rule.category || 'Other';
    if (!map[comp]) map[comp] = { component: comp, rule_count: 0, rules: [] };
    map[comp].rules.push(rule);
    map[comp].rule_count += 1;
  });
  const ordered = COMPONENT_ORDER.filter(c => map[c]).map(c => map[c]);
  Object.keys(map).forEach(c => {
    if (!COMPONENT_ORDER.includes(c)) ordered.push(map[c]);
  });
  return ordered;
}

export function resolveComponents(apiData) {
  if (Array.isArray(apiData) && apiData.length > 0) return apiData;
  return STATIC_COMPONENTS;
}
