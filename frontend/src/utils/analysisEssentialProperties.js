/**
 * Analysis-essential drawer Overview fields.
 *
 * Derived from backend TECHNICAL_FETCH_SPEC.technical_fields where `rules` is non-empty
 * (fields consumed by optimization rules / assessment JSON), plus core identity/status.
 *
 * Examples (see resource_profile.py in each IT service):
 * - compute/disk: diskState, diskSizeGB, diskIOPSReadWrite, diskMBpsReadWrite, managedBy,
 *   timeCreated, lastOwnershipUpdateTime, sku — rules DISK_UNATTACHED, DISK_OVERSIZE, etc.
 * - compute/vm: hardwareProfile.vmSize, powerState, timeCreated, Environment tag —
 *   rules VM_IDLE, VM_OVERSIZE, VM_RIGHTSIZE_FAMILY, etc.
 * - storage/account: accessTier, kind, sku.name — rules STORAGE_HOT_TIER, STORAGE_NO_LIFECYCLE, etc.
 *
 * Regenerate data: python3 scripts/generate-analysis-essential-properties.py
 */
import analysisData from './analysisEssentialProperties.data.json';
import { resolveDrawerCanonicalType } from './drawerTrendMetrics';

const { coreMatchers, byCanonicalType } = analysisData;

const CORE_MATCHERS = new Set(coreMatchers.map(normalizeToken));

function normalizeToken(value) {
  return String(value || '').trim().toLowerCase().replace(/[._\s-]+/g, '');
}

function rowTokens(row) {
  const tokens = new Set();
  const key = normalizeToken(row?.key);
  const factKey = normalizeToken(row?.fact_key);
  const label = normalizeToken(row?.label);
  if (key) tokens.add(key);
  if (factKey) tokens.add(factKey);
  if (label) tokens.add(label);
  const leaf = String(row?.fact_key || row?.key || '').split('.').pop();
  if (leaf) tokens.add(normalizeToken(leaf));
  return tokens;
}

function tokensMatchAny(tokens, patterns) {
  for (const pattern of patterns) {
    const normalized = normalizeToken(pattern);
    if (!normalized) continue;
    if (tokens.has(normalized)) return true;
    for (const token of tokens) {
      if (token.includes(normalized) || normalized.includes(token)) return true;
    }
  }
  return false;
}

/** Core identity/status fields always shown in Overview. */
export function getCoreOverviewMatchers() {
  return [...coreMatchers];
}

/** Per-type analysis field metadata from backend technical_fields with rules. */
export function getAnalysisFieldsForType(canonicalType = '') {
  const key = String(canonicalType || '').trim().toLowerCase();
  return byCanonicalType[key] || { factKeys: [], matchers: [], labels: [] };
}

/**
 * True when a drawer essentials/property row should appear in Overview.
 * Informational synced ARM metadata without rule references is excluded.
 */
export function isAnalysisEssentialRow(row, { canonicalType = '', resource = null, apiPath = '' } = {}) {
  if (!row?.label) return false;

  const resolvedType = canonicalType || resolveDrawerCanonicalType(resource, apiPath);
  const tokens = rowTokens(row);

  if (tokensMatchAny(tokens, coreMatchers)) return true;

  const typeSpec = getAnalysisFieldsForType(resolvedType);
  if (typeSpec.matchers.length && tokensMatchAny(tokens, typeSpec.matchers)) return true;
  if (typeSpec.labels.length && tokensMatchAny(tokens, typeSpec.labels)) return true;
  if (typeSpec.factKeys.length) {
    for (const factKey of typeSpec.factKeys) {
      if (tokens.has(normalizeToken(factKey))) return true;
    }
  }

  return false;
}

/**
 * Split property rows into analysis-essential (Overview) and informational overflow.
 * @returns {{ essential: object[], overflow: object[] }}
 */
export function partitionAnalysisEssentialRows(rows, options = {}) {
  const essential = [];
  const overflow = [];
  for (const row of rows || []) {
    if (isAnalysisEssentialRow(row, options)) {
      essential.push(row);
    } else {
      overflow.push(row);
    }
  }
  return { essential, overflow };
}
