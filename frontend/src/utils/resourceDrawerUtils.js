import { toDisplayText } from './formatDisplay';
import { formatDateTime } from './format';
import { shouldSkipOverviewTiles } from '../it-services/registry';

function addTile(tiles, label, rawValue) {
  const value = toDisplayText(rawValue);
  if (!value || value === '—') return;
  tiles.push({ label, value });
}

const PROPERTY_TILES = [
  ['Tier', ['tier', 'accessTier', 'access_tier']],
  ['Kind', ['kind']],
  ['Size', ['vmSize', 'vm_size', 'size', 'hardwareProfile.vmSize']],
  ['Version', ['kubernetesVersion', 'kubernetes_version', 'version']],
  ['Provisioning state', ['provisioningState', 'provisioning_state']],
];

function addPropertyTiles(tiles, properties) {
  if (!properties || typeof properties !== 'object') return;
  for (const [label, keys] of PROPERTY_TILES) {
    if (tiles.some((t) => t.label === label)) continue;
    for (const key of keys) {
      const val = properties[key];
      if (val != null && val !== '') {
        addTile(tiles, label, val);
        break;
      }
    }
  }
}

/** Inventory tiles for resource insight drawer (cost lives in header KPI strip only). */
export function getDrawerOverviewTiles(resource, { apiPath = '' } = {}) {
  if (!resource) return [];

  if (shouldSkipOverviewTiles(resource, apiPath)) {
    return [];
  }

  const tiles = [];

  addTile(tiles, 'Location', resource.location);
  addTile(tiles, 'Resource group', resource.resourceGroup || resource.resource_group);
  addTile(tiles, 'State', resource.state || resource._state);
  addTile(tiles, 'SKU', resource.sku || resource._sku);
  addTile(tiles, 'Type', resource.type);
  if (resource.syncedAt) {
    addTile(tiles, 'Last synced', formatDateTime(resource.syncedAt));
  }
  if (resource._version) addTile(tiles, 'Version', resource._version);
  if (resource._nodeCount != null) addTile(tiles, 'Nodes', String(resource._nodeCount));

  addPropertyTiles(tiles, resource.properties);

  return tiles.map((tile, index) => ({ ...tile, key: tile.key || `tile-${index}` }));
}
