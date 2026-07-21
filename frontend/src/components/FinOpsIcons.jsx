import React from 'react';
import {
  Cpu, Boxes, HardDrive, Network, Database, Shield, DollarSign,
  AlertOctagon, AlertTriangle, Info, CircleAlert,
  Server, Container, Globe, AppWindow, KeyRound, Layers, GitBranch,
  Package, Filter, FolderOpen, CheckCircle2, Eye, XCircle, X,
  MapPin, Lightbulb, BarChart3, Target, FileJson, Ban,
} from 'lucide-react';
import AssetIcon from './AssetIcon';
import { iconKeyForAzureType, iconKeyForCategory, iconKeyForCanonicalType } from '../config/azureIconRegistry';

export const CATEGORY_META = {
  COMPUTE:    { Icon: Cpu,       color: '#60a5fa', label: 'Compute' },
  KUBERNETES: { Icon: Boxes,     color: '#a78bfa', label: 'Kubernetes' },
  STORAGE:    { Icon: HardDrive, color: '#fbbf24', label: 'Storage' },
  NETWORK:    { Icon: Network,   color: '#34d399', label: 'Network' },
  DATABASE:   { Icon: Database,  color: '#f87171', label: 'Database' },
  SECURITY:   { Icon: Shield,    color: '#fb923c', label: 'Security' },
  COST:       { Icon: DollarSign,color: '#22d3ee', label: 'Cost' },
};

export const SEVERITY_META = {
  CRITICAL: { Icon: AlertOctagon, color: 'var(--danger)' },
  HIGH:     { Icon: AlertTriangle, color: 'var(--warning)' },
  MEDIUM:   { Icon: CircleAlert, color: '#fbbf24' },
  LOW:      { Icon: Info, color: 'var(--success)' },
  INFO:     { Icon: Info, color: 'var(--primary)' },
};

export const AZURE_TYPE_META = {
  'Microsoft.Compute/virtualMachines':          { Icon: Server,    color: '#0078d4' },
  'Microsoft.Compute/disks':                    { Icon: HardDrive, color: '#5c2d91' },
  'Microsoft.ContainerService/managedClusters': { Icon: Boxes,     color: '#326ce5' },
  'Microsoft.ContainerRegistry/registries':     { Icon: Container, color: '#326ce5' },
  'Microsoft.Storage/storageAccounts':          { Icon: HardDrive, color: '#0078d4' },
  'Microsoft.Web/sites':                        { Icon: AppWindow, color: '#0090d2' },
  'Microsoft.Sql/servers':                      { Icon: Database,  color: '#a91d22' },
  'Microsoft.DBforPostgreSQL/flexibleServers':  { Icon: Database,  color: '#336791' },
  'Microsoft.DocumentDB/databaseAccounts':      { Icon: Database,  color: '#a91d22' },
  'Microsoft.KeyVault/vaults':                  { Icon: KeyRound,  color: '#107c10' },
  'Microsoft.Network/publicIPAddresses':        { Icon: Globe,     color: '#0063b1' },
  'Microsoft.Network/loadBalancers':            { Icon: Layers,    color: '#0063b1' },
  'Microsoft.Network/applicationGateways':      { Icon: GitBranch, color: '#0063b1' },
  'Microsoft.Network/networkSecurityGroups':    { Icon: Shield,    color: '#0063b1' },
};

function metaForCategory(category) {
  const key = (category || '').toUpperCase();
  return CATEGORY_META[key] || { Icon: Package, color: 'var(--text3)', label: category };
}

function metaForAzureType(type) {
  if (!type) return { Icon: Package, color: '#5a6070' };
  const exact = AZURE_TYPE_META[type];
  if (exact) return exact;
  if (type.includes('Compute')) return AZURE_TYPE_META['Microsoft.Compute/virtualMachines'];
  if (type.includes('ContainerService')) return AZURE_TYPE_META['Microsoft.ContainerService/managedClusters'];
  if (type.includes('Storage')) return AZURE_TYPE_META['Microsoft.Storage/storageAccounts'];
  if (type.includes('Network')) return AZURE_TYPE_META['Microsoft.Network/publicIPAddresses'];
  if (type.includes('Sql') || type.includes('Database')) return AZURE_TYPE_META['Microsoft.Sql/servers'];
  if (type.includes('KeyVault')) return AZURE_TYPE_META['Microsoft.KeyVault/vaults'];
  return { Icon: Package, color: '#5a6070' };
}

export function IconChip({ Icon, color, size = 16, bg = true, assetSrc = null, iconKey = null }) {
  const dim = Math.round(size * 1.75);
  const lucideFallback = Icon ? <Icon size={size} strokeWidth={2} /> : null;

  return (
    <span
      className="icon-chip"
      style={{
        width: dim,
        height: dim,
        background: bg ? `${color}22` : 'transparent',
        color,
      }}
    >
      {(iconKey || assetSrc) ? (
        <AssetIcon iconKey={iconKey} src={assetSrc} size={size} fallback={lucideFallback} />
      ) : lucideFallback}
    </span>
  );
}

export function CategoryIcon({ category, size = 14, showLabel = false }) {
  const { Icon, color, label } = metaForCategory(category);
  const key = iconKeyForCategory(category);
  return (
    <span className="icon-inline">
      <IconChip Icon={Icon} color={color} size={size} iconKey={key} />
      {showLabel && <span>{label || category}</span>}
    </span>
  );
}

export function SeverityIcon({ severity, size = 13, showLabel = false }) {
  const meta = SEVERITY_META[severity] || SEVERITY_META.INFO;
  const { Icon, color } = meta;
  return (
    <span className="icon-inline">
      <Icon size={size} style={{ color, flexShrink: 0 }} strokeWidth={2.25} />
      {showLabel && <span>{severity}</span>}
    </span>
  );
}

export function AzureResourceIcon({ type, size = 28, src = null }) {
  const iconKey = src || iconKeyForCanonicalType(type) || iconKeyForAzureType(type);
  const { Icon, color } = metaForAzureType(type);
  const lucideFallback = (
    <span
      className="icon-chip icon-chip--resource"
      style={{
        width: size,
        height: size,
        background: color,
        color: '#fff',
        borderRadius: Math.round(size * 0.22),
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Icon size={Math.round(size * 0.48)} strokeWidth={2} />
    </span>
  );

  return (
    <AssetIcon
      iconKey={iconKey}
      size={size}
      fallback={lucideFallback}
    />
  );
}

export function StatusIcon({ status, size = 13 }) {
  const map = {
    open:         { Icon: CircleAlert, color: 'var(--danger)' },
    acknowledged: { Icon: Eye, color: 'var(--warning)' },
    resolved:     { Icon: CheckCircle2, color: 'var(--success)' },
    ignored:      { Icon: Ban, color: 'var(--text3)' },
  };
  const { Icon, color } = map[status] || map.open;
  return <Icon size={size} style={{ color }} strokeWidth={2} />;
}

export {
  Filter, FolderOpen, DollarSign, Target, BarChart3, Lightbulb,
  MapPin, FileJson, Eye, CheckCircle2, XCircle, X, Server,
};
