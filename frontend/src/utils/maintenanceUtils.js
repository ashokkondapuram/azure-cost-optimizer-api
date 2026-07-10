import { formatDateTimeUtc, formatIsoDate } from './format';

export const SOURCE_LABEL = {
  health_event: 'Service health',
  vm: 'Virtual machine',
  vmss: 'VM scale set',
  vmss_instance: 'VMSS instance',
};

export const CATEGORY_OPTIONS = [
  { value: '', label: 'All types' },
  { value: 'health_event', label: 'Service health' },
  { value: 'vm', label: 'Virtual machines' },
  { value: 'vmss', label: 'VM scale sets' },
  { value: 'vmss_instance', label: 'VMSS instances' },
];

/** Present resource-type categories only (maps legacy activity_log rows to VM / VMSS). */
export function maintenanceCategory(item) {
  if (!item) return 'vm';
  const source = item.source;
  if (source === 'activity_log') {
    if (item.resource_type === 'VM scale set') return 'vmss';
    if (item.resource_type === 'Virtual machine') return 'vm';
    return 'vm';
  }
  if (source in SOURCE_LABEL) return source;
  return 'vm';
}

export function categoryLabel(item) {
  return SOURCE_LABEL[maintenanceCategory(item)] || item.resource_type || 'Maintenance';
}

export const URGENCY_LABEL = {
  soon: 'Within 48 hours',
  upcoming: 'This week',
  scheduled: 'Scheduled',
  action: 'Action needed',
  completed: 'Completed',
  none: 'No window',
};

export const MAINTENANCE_SOURCE_ICON = {
  health_event: 'serviceHealth',
  vm: 'virtualMachine',
  vmss: 'vmScaleSets',
  vmss_instance: 'vmScaleSets',
};

export function parseWindowStart(item) {
  if (!item?.window_start) return null;
  const d = new Date(item.window_start);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function parseWindowEnd(item) {
  if (!item?.window_end) return null;
  const d = new Date(item.window_end);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** True when the maintenance window has fully ended (UTC). */
export function isWindowCompleted(item, nowMs = Date.now()) {
  const end = parseWindowEnd(item);
  if (end) return end.getTime() < nowMs;

  const start = parseWindowStart(item);
  if (!start) return false;

  if (item.source === 'activity_log' || item.origin === 'activity_log') {
    return start.getTime() < nowMs;
  }

  return start.getTime() < nowMs;
}

/** True when the window is in the future or still in progress. */
export function isUpcomingWindow(item, nowMs = Date.now()) {
  if (item.pending_model_update || item.pending_model_updates) return true;

  const start = parseWindowStart(item);
  const end = parseWindowEnd(item);
  if (!start && !end) return false;

  if (end) return end.getTime() >= nowMs;
  if (start) return start.getTime() >= nowMs;
  return false;
}

/** Earliest upcoming maintenance item by window start (UTC). */
export function findNextMaintenanceWindow(items, nowMs = Date.now()) {
  let best = null;
  let bestStartMs = Infinity;

  for (const item of items) {
    if (!isUpcomingWindow(item, nowMs)) continue;
    const start = parseWindowStart(item);
    if (!start) {
      if (item.pending_model_update || item.pending_model_updates) {
        const sortMs = nowMs;
        if (sortMs < bestStartMs) {
          bestStartMs = sortMs;
          best = item;
        }
      }
      continue;
    }

    const startMs = start.getTime();
    const sortMs = startMs >= nowMs ? startMs : nowMs;
    if (sortMs < bestStartMs) {
      bestStartMs = sortMs;
      best = item;
    }
  }

  return best;
}

export function urgencyFor(item, nowMs = Date.now()) {
  if (item.pending_model_update || item.pending_model_updates) return 'action';

  const start = parseWindowStart(item);
  const end = parseWindowEnd(item);

  if (!start && !end) return 'none';

  if (isWindowCompleted(item, nowMs)) return 'completed';

  if (start && start.getTime() <= nowMs && end && end.getTime() > nowMs) {
    return 'soon';
  }

  if (!start) return 'scheduled';

  const hours = (start.getTime() - nowMs) / (1000 * 60 * 60);
  if (hours < 48) return 'soon';
  if (hours < 168) return 'upcoming';
  return 'scheduled';
}

export function formatMaintenanceWindow(start, end) {
  if (!start && !end) return '—';
  if (start && end) return `${formatDateTimeUtc(start)} – ${formatDateTimeUtc(end)}`;
  if (start) return `From ${formatDateTimeUtc(start)}`;
  return `Until ${formatDateTimeUtc(end)}`;
}

export function windowSortKey(item) {
  if (item.pending_model_update || item.pending_model_updates) return '0000';
  return item.window_start || item.event_timestamp || '9999';
}

export function groupMaintenanceByResource(items) {
  const map = new Map();

  for (const item of items) {
    const key = (
      item.resource_id
      || `${item.resource_group || ''}/${item.resource_name || item.title || item.id}`
    ).toLowerCase();

    if (!map.has(key)) {
      map.set(key, {
        key,
        resource_id: item.resource_id,
        resource_name: item.resource_name || item.title || 'Unknown resource',
        resource_group: item.resource_group,
        location: item.location,
        resource_type: item.resource_type,
        items: [],
      });
    }
    map.get(key).items.push(item);
  }

  return [...map.values()]
    .map((group) => ({
      ...group,
      items: [...group.items].sort((a, b) => windowSortKey(a).localeCompare(windowSortKey(b))),
    }))
    .sort((a, b) => windowSortKey(a.items[0]).localeCompare(windowSortKey(b.items[0])));
}

export function iconKeyForMaintenanceItem(item) {
  if (!item) return 'virtualMachine';
  const source = item.source;
  if (source in MAINTENANCE_SOURCE_ICON) {
    return MAINTENANCE_SOURCE_ICON[source];
  }
  if (source === 'activity_log') {
    return MAINTENANCE_SOURCE_ICON[maintenanceCategory(item)] || 'virtualMachine';
  }
  if (item.resource_id) return null;
  return 'virtualMachine';
}

export function timelineDateLabel(item) {
  const start = parseWindowStart(item);
  if (!start) return 'Pending';
  if (isWindowCompleted(item)) return 'Completed';
  return formatIsoDate(item.window_start.slice(0, 10));
}
