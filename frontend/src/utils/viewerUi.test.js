import {
  genericLoadingMessage,
  inventoryListSubtitle,
  inventorySourceLabel,
  resourceLoadingMessage,
} from './viewerUi';

describe('viewerUi', () => {
  it('hides database and Azure source labels for viewers', () => {
    expect(inventorySourceLabel({ isAdmin: false, isLive: true })).toBe('Inventory');
    expect(inventorySourceLabel({ isAdmin: true, isLive: false })).toBe('Synced from database');
  });

  it('uses generic inventory subtitles for viewers', () => {
    expect(inventoryListSubtitle({
      isAdmin: false,
      isLive: true,
      suffix: '3 of 10 VMs',
    })).toBe('3 of 10 VMs');
    expect(inventoryListSubtitle({
      isAdmin: true,
      isLive: false,
      suffix: '3 of 10 VMs',
    })).toBe('from database · 3 of 10 VMs');
  });

  it('uses generic loading messages for viewers', () => {
    expect(resourceLoadingMessage(false, { isLive: true, label: 'disks' })).toBe('Loading disks…');
    expect(resourceLoadingMessage(true, { isLive: true, label: 'disks' })).toBe('Fetching disks from Azure…');
    expect(genericLoadingMessage(false, 'Loading run history…')).toBe('Loading…');
    expect(genericLoadingMessage(true, 'Loading run history…')).toBe('Loading run history…');
  });
});
