import React, { useMemo } from 'react';
import { Activity, HardDrive } from 'lucide-react';
import ArmResourceLink from '../../../components/ArmResourceLink';
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

function DiskPropertyValue({ tile }) {
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

  return value;
}

function DiskTileGrid({ tiles, className = '' }) {
  if (!tiles.length) return null;

  return (
    <div
      className={`insight-drawer__overview-grid insight-drawer__overview-grid--compact insight-drawer__disk-props-grid ${className}`.trim()}
      role="list"
    >
      {tiles.map((tile) => (
        <div
          key={tile.key}
          role="listitem"
          className={`insight-drawer__overview-tile${tile.tone ? ` insight-drawer__overview-tile--${tile.tone}` : ''}`}
        >
          <span className="insight-drawer__overview-label">{tile.label}</span>
          <span className="insight-drawer__overview-value">
            <DiskPropertyValue tile={tile} />
          </span>
        </div>
      ))}
    </div>
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
  const statusMessage = useMemo(
    () => getDiskMetricsStatusMessage(metricsData, metricsError),
    [metricsData, metricsError],
  );

  if (!drawerSections.length && !usageTiles.length && !metricsLoading) return null;

  return (
    <section className="insight-drawer__disk-props" aria-label="Disk properties and usage">
      {drawerSections.map((section) => (
        <React.Fragment key={section.id}>
          <div className={`insight-drawer__disk-props-header${section.id === 'provisioned' ? ' insight-drawer__disk-props-header--capacity' : ''}`}>
            {section.id === 'identity' && <HardDrive size={13} aria-hidden />}
            <span>{section.label}</span>
          </div>
          <DiskTileGrid tiles={section.tiles} />
        </React.Fragment>
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

      {!metricsLoading && usageTiles.length > 0 && (
        <DiskTileGrid tiles={usageTiles} className="insight-drawer__disk-props-grid--usage" />
      )}

      {!metricsLoading && !usageTiles.length && statusMessage && (
        <p className="insight-drawer__disk-props-hint text-muted">
          {metricsError ? getErrorMessage(metricsError, statusMessage) : statusMessage}
        </p>
      )}
    </section>
  );
}
