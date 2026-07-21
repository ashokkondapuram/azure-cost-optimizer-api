/** Match AKS agent pools to backing VM scale sets (mirrors it_services.containers_aks.vmss_match). */

function resourceGroupFromArmId(resourceId) {
  const parts = String(resourceId || '').split('/').filter(Boolean);
  const idx = parts.findIndex((part) => part.toLowerCase() === 'resourcegroups');
  return idx >= 0 ? parts[idx + 1] : '';
}

export function vmssNamePrefixForPool(poolName) {
  return `aks-${String(poolName || '').trim().toLowerCase()}-`;
}

export function matchPoolVmss(poolName, vmssList = []) {
  if (!poolName || !vmssList?.length) return null;

  const poolLower = String(poolName).trim().toLowerCase();
  const prefix = vmssNamePrefixForPool(poolName);
  const exact = `aks-${poolLower}`;

  const candidates = [];
  for (const vmss of vmssList) {
    const name = String(vmss?.name || '').trim().toLowerCase();
    if (!name) continue;
    if (name.startsWith(prefix) || name === exact || name.startsWith(`${exact}-`)) {
      candidates.push({ nameLength: name.length, vmss });
    }
  }

  if (!candidates.length) return null;
  candidates.sort((a, b) => a.nameLength - b.nameLength);
  return candidates[0].vmss;
}

export function filterVmssForResourceGroup(vmssList = [], resourceGroup) {
  const rgLower = String(resourceGroup || '').trim().toLowerCase();
  if (!rgLower) return [];
  return vmssList.filter((vmss) => {
    const rid = vmss?.id || vmss?.resource_id || '';
    return resourceGroupFromArmId(rid).toLowerCase() === rgLower;
  });
}

export function vmssNameFromArmId(resourceId) {
  const parts = String(resourceId || '').split('/').filter(Boolean);
  return parts[parts.length - 1] || '';
}

export function resolvePoolVmssRef(pool, vmssByPool = {}) {
  const props = pool?.properties || {};
  const direct = pool?.virtualMachineScaleSet || props.virtualMachineScaleSet;
  const directId = typeof direct === 'string'
    ? direct
    : direct?.id;
  if (directId && directId.includes('/')) {
    const directName = (typeof direct === 'object' && direct?.name)
      ? direct.name
      : vmssNameFromArmId(directId);
    return {
      vmssId: directId,
      vmssName: directName,
      vmssSource: 'synced',
    };
  }

  const poolName = String(pool?.name || '').trim();
  const mapped = poolName ? vmssByPool?.[poolName] : null;
  if (mapped) {
    const mappedId = typeof mapped === 'string' ? mapped : mapped?.id;
    if (mappedId && String(mappedId).includes('/')) {
      const mappedName = (typeof mapped === 'object' && mapped?.name)
        ? mapped.name
        : vmssNameFromArmId(mappedId);
      return {
        vmssId: mappedId,
        vmssName: mappedName,
        vmssSource: 'synced',
      };
    }
  }

  return { vmssId: null, vmssName: null, vmssSource: null };
}
