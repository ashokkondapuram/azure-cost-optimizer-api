import {
  isArmResourceId,
  shortArmResourceLabel,
  azurePortalUrl,
  normalizeArmResourceId,
  inventoryInspectLink,
  actionCentreHubLink,
  drawerSectionToHubSection,
  parseComputeHostAttachment,
} from './armResourceLinks';

const DISK_ID = '/subscriptions/93ca908b-5732-440d-b712-f6d7951951c0/resourceGroups/MC_ziov2rg1eu2_ziov2rg1eu2_eastus2/providers/Microsoft.Compute/disks/cso-54802-pgcore';
const VM_ID = '/subscriptions/93ca908b-5732-440d-b712-f6d7951951c0/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachines/vm-web-01';
const VMSS_INSTANCE_ID = '/subscriptions/93ca908b-5732-440d-b712-f6d7951951c0/resourceGroups/rg-prod/providers/Microsoft.Compute/virtualMachineScaleSets/app-vmss/virtualMachines/3';

describe('armResourceLinks', () => {
  test('detects ARM resource IDs', () => {
    expect(isArmResourceId(DISK_ID)).toBe(true);
    expect(isArmResourceId(DISK_ID.slice(1))).toBe(true);
    expect(isArmResourceId('cso-54802-pgcore')).toBe(false);
    expect(isArmResourceId('/subscriptions/x')).toBe(false);
  });

  test('shortens resource ID to resource name', () => {
    expect(shortArmResourceLabel(DISK_ID)).toBe('cso-54802-pgcore');
  });

  test('builds Azure portal URLs', () => {
    expect(azurePortalUrl(DISK_ID)).toBe(
      `https://portal.azure.com/#resource${DISK_ID}`,
    );
    expect(azurePortalUrl('not-an-arm-id')).toBeNull();
  });

  test('normalizes leading slash', () => {
    expect(normalizeArmResourceId(DISK_ID.slice(1))).toBe(DISK_ID);
  });

  test('builds action centre inspect links', () => {
    const link = inventoryInspectLink(DISK_ID);
    expect(link).toContain('/action-centre?');
    expect(link).toContain('inspect=1');
    expect(link).toContain('section=advanced-analysis');
    expect(link).toContain(`resource=${encodeURIComponent(DISK_ID)}`);
    expect(inventoryInspectLink('not-an-arm-id')).toBeNull();
  });

  test('maps drawer sections to hub deep links', () => {
    expect(drawerSectionToHubSection('analysis')).toBe('advanced-analysis');
    expect(drawerSectionToHubSection('properties')).toBe('technical-properties');
    expect(drawerSectionToHubSection('metrics')).toBe('vm-metrics');
    expect(drawerSectionToHubSection('actions')).toBe('proposed-actions');
    const link = actionCentreHubLink(DISK_ID, { sectionId: 'analysis' });
    expect(link).toContain('inspect=1');
    expect(link).toContain('section=advanced-analysis');
    expect(link).toContain(`resource=${encodeURIComponent(DISK_ID)}`);
  });

  test('parses VM and VMSS disk host attachments', () => {
    const vm = parseComputeHostAttachment(VM_ID);
    expect(vm?.kind).toBe('vm');
    expect(vm?.displayLabel).toBe('vm-web-01');
    expect(vm?.inventoryLink).toContain('/action-centre?');

    const vmssInstance = parseComputeHostAttachment(VMSS_INSTANCE_ID);
    expect(vmssInstance?.kind).toBe('vmss_instance');
    expect(vmssInstance?.displayLabel).toBe('app-vmss / instance 3');
    expect(vmssInstance?.inventoryLink).toContain('/action-centre?');
    expect(vmssInstance?.inventoryLink).toContain('app-vmss');
  });
});
