import React, { useMemo } from 'react';
import { Activity } from 'lucide-react';
import ArmResourceLink from '../../../components/ArmResourceLink';
import DrawerEssentials from '../../../components/DrawerEssentials';
import DiskHostAttachmentLink from './DiskHostAttachmentLink';
import { isArmResourceId } from '../../../utils/armResourceLinks';
import { getErrorMessage } from '../../../api/errors';
import ResourceMetricsTimespanFilter from '../../../components/ResourceMetricsTimespanFilter';
import { DrawerSectionSkeleton } from '../../../components/DrawerBodySkeleton';
import {
  diskUsageSectionLabel,
  getDiskDrawerSections,
  getDiskMetricsStatusMessage,
  getDiskUsageTiles,
} from '../utils/diskUtils';

function DiskEssentialValue({ tile }) {
  if (tile.attachment || tile.linkValue) {
    return (
      <DiskHostAttachmentLink
        attachment={tile.attachment}
        fallbackResourceId={tile.linkValue}
      />
    );
  }

  const { value, linkValue } = tile;
  const linkTarget = [linkValue, value].find((candidate) => (
    typeof candidate === 'string' && isArmResourceId(candidate)
  ));

  if (linkTarget) {
    return <ArmResourceLink resourceId={linkTarget} />;
  }

  return tile.value;
}

function diskTileToEssentialRow(tile) {
  const hasCustomValue = tile.attachment || tile.linkValue
    || [tile.linkValue, tile.value].some((candidate) => (
      typeof candidate === 'string' && isArmResourceId(candidate)
    ));

  return {
    key: tile.key,
    label: tile.label,
    value: tile.value,
    tone: tile.tone,
    render: hasCustomValue ? <DiskEssentialValue tile={tile} /> : undefined,
  };
}

function DiskEssentialsSection({ section }) {
  const rows = useMemo(
    () => (section.tiles || []).map((tile) => diskTileToEssentialRow(tile)),
    [section.tiles],
  );
  if (!rows.length) return null;
  return (
    <DrawerEssentials
      rows={rows}
      title={section.label}
      className="insight-drawer__essentials--disk"
    />
  );
}

export default function DiskPropertiesPanel({
  resource,
  metricsData = null,
  metricsLoading = false,
  metricsError = null,
  timespan,
  onTimespanChange,
}) {
  const drawerSections = useMemo(
    () => getDiskDrawerSections(resource, metricsData),
    [resource, metricsData],
  );
  const usageTiles = useMemo(
    () => getDiskUsageTiles(metricsData, { resource }),
    [metricsData, resource],
  );
  const usageRows = useMemo(
    () => usageTiles.map((tile) => diskTileToEssentialRow(tile)),
    [usageTiles],
  );
  const statusMessage = useMemo(
    () => getDiskMetricsStatusMessage(metricsData, metricsError),
    [metricsData, metricsError],
  );

  if (!drawerSections.length && !usageRows.length && !metricsLoading) return null;

  return (
    <section className="insight-drawer__disk-props" aria-label="Disk details">
      {drawerSections.map((section) => (
        <DiskEssentialsSection key={section.id} section={section} />
      ))}

      <div className="insight-drawer__disk-props-header insight-drawer__disk-props-header--usage">
        <Activity size={13} aria-hidden />
        <span>{diskUsageSectionLabel(timespan || metricsData?.timespan)}</span>
        {timespan && onTimespanChange && (
          <ResourceMetricsTimespanFilter
            value={timespan}
            onChange={onTimespanChange}
          />
        )}
      </div>

      {metricsLoading && <DrawerSectionSkeleton rows={3} />}

      {!metricsLoading && usageRows.length > 0 && (
        <DrawerEssentials
          rows={usageRows}
          title="Usage"
          hideTitle
          className="insight-drawer__essentials--disk insight-drawer__essentials--usage"
        />
      )}

      {!metricsLoading && !usageRows.length && statusMessage && (
        <p className="insight-drawer__disk-props-hint text-muted">
          {metricsError ? getErrorMessage(metricsError, statusMessage) : statusMessage}
        </p>
      )}
    </section>
  );
}
