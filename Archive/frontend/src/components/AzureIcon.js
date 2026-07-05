import React from 'react';

const BG_MAP = {
  'Microsoft.Compute/virtualMachines':           '#0078d4',
  'Microsoft.Compute/disks':                     '#5c2d91',
  'Microsoft.ContainerService/managedClusters':  '#326ce5',
  'Microsoft.Storage/storageAccounts':           '#0078d4',
  'Microsoft.Web/sites':                         '#0090d2',
  'Microsoft.Sql/servers':                       '#a91d22',
  'Microsoft.DBforPostgreSQL/flexibleServers':   '#336791',
  'Microsoft.KeyVault/vaults':                   '#107c10',
  'Microsoft.Network/publicIPAddresses':         '#0063b1',
};

const EMOJI_MAP = {
  'Microsoft.Compute/virtualMachines':           '🖥',
  'Microsoft.Compute/disks':                     '💽',
  'Microsoft.ContainerService/managedClusters':  '⎈',
  'Microsoft.Storage/storageAccounts':           '🪣',
  'Microsoft.Web/sites':                         '🌐',
  'Microsoft.Sql/servers':                       '🗄',
  'Microsoft.DBforPostgreSQL/flexibleServers':   '🐘',
  'Microsoft.KeyVault/vaults':                   '🔑',
  'Microsoft.Network/publicIPAddresses':         '🌍',
};

export default function AzureIcon({ type, size = 28, style = {} }) {
  const bg    = BG_MAP[type]  || '#5a6070';
  const emoji = EMOJI_MAP[type] || '📦';
  return (
    <span style={{
      display:'inline-flex', alignItems:'center', justifyContent:'center',
      width:size, height:size, borderRadius:Math.round(size*0.22),
      background:bg, fontSize:size*0.52, flexShrink:0, ...style
    }}>
      {emoji}
    </span>
  );
}
