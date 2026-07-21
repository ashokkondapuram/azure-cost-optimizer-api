/**
 * Shared assessment JSON loader — one assessment file per resource type.
 * Mirrors frontend/src/disks/diskAssessment.js for all resource modules.
 */

const ASSESSMENT_MODULES = {
  'compute/disk': () => import('../disks/data/disk-assessment.json'),
  'database/cosmosdb': () => import('../cosmosdb/data/cosmosdb-assessment.json'),
};

const assessmentCache = new Map();

export function isV2Assessment(assessment) {
  const schema = assessment?.schema_version || assessment?.schemaVersion || '';
  return String(schema).startsWith('2');
}

export async function loadAssessment(canonicalType) {
  const key = (canonicalType || '').trim().toLowerCase();
  if (assessmentCache.has(key)) {
    return assessmentCache.get(key);
  }
  const loader = ASSESSMENT_MODULES[key];
  if (!loader) {
    return null;
  }
  const mod = await loader();
  const assessment = mod.default || mod;
  assessmentCache.set(key, assessment);
  return assessment;
}

export function propertyGroupsFromAssessment(assessment) {
  if (!assessment) return [];
  if (isV2Assessment(assessment)) {
    return (assessment.azure_properties?.groups || []).map((group) => ({
      key: group.group,
      title: group.title || group.group,
      properties: (group.properties || []).map((prop) => ({
        key: prop.arm_path?.split('.').pop() || prop.arm_path,
        armPath: prop.arm_path,
        label: prop.label,
        type: prop.type,
        unit: prop.unit,
      })),
    }));
  }
  const props = assessment.resourceProperties || [];
  return [{
    key: 'configuration',
    title: 'Configuration',
    properties: props
      .filter((p) => !['id', 'name', 'type', 'location', 'tags'].includes(p))
      .map((p) => ({
        key: String(p).replace(/^properties\./, ''),
        armPath: String(p).startsWith('properties.') ? p : `properties.${p}`,
        label: String(p).split('.').pop(),
        type: 'string',
      })),
  }];
}

export function rulesFromAssessment(assessment) {
  if (!assessment) return [];
  if (isV2Assessment(assessment)) {
    return assessment.rules || [];
  }
  return [
    ...(assessment.recommendationRules || []),
    ...(assessment.assessmentRules || []),
  ];
}

export function getRuleById(assessment, ruleId) {
  const id = String(ruleId || '').trim();
  if (!id) return null;
  const rules = rulesFromAssessment(assessment);
  return rules.find((r) => (r.rule_id || r.id) === id)
    || rules.find((r) => (r.rule_id || r.id) === id.replace(/_EXTENDED$/, ''))
    || null;
}

export function optimizationThresholds(assessment) {
  return assessment?.optimization_thresholds || {};
}

export function listColumnsFromAssessment(assessment, { maxColumns = 6 } = {}) {
  const groups = propertyGroupsFromAssessment(assessment);
  const columns = [];
  for (const group of groups) {
    for (const prop of group.properties) {
      columns.push({ ...prop, group: group.key });
      if (columns.length >= maxColumns) return columns;
    }
  }
  return columns;
}
