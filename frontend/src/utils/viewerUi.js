/** Viewer-safe copy — hide database, Azure sync, and job internals. */

const TECHNICAL_LOADING_RE = /database|azure|sync|analysis job|run history|run findings|snapshot detail/i;

export function inventorySourceLabel({ isAdmin, isLive } = {}) {
  if (!isAdmin) return 'Inventory';
  return isLive ? 'Live from Azure' : 'Synced from database';
}

export function inventoryListSubtitle({ isAdmin, isLive, suffix }) {
  if (!suffix) return '';
  if (!isAdmin) return suffix;
  const source = isLive ? 'live from Azure' : 'from database';
  return `${source} · ${suffix}`;
}

export function resourceLoadingMessage(isAdmin, { isLive = false, label = 'resources' } = {}) {
  if (!isAdmin) return `Loading ${label}…`;
  if (isLive) return `Fetching ${label} from Azure…`;
  return `Loading ${label} from database…`;
}

export function genericLoadingMessage(isAdmin, message = 'Loading…') {
  if (isAdmin) return message;
  if (TECHNICAL_LOADING_RE.test(message)) return 'Loading…';
  return message;
}
