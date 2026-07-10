/**
 * Sidebar path visibility — mirrors backend nav_access policy.
 */
import {
  OVERVIEW_NAV,
  ADVANCED_NAV_GROUPS,
  ADVANCED_TOOLS_NAV,
  OPTIMIZATION_NAV_ITEMS,
  SYSTEM_NAV,
  RESOURCE_PAGES,
  NAV_RESOURCE_GROUPS,
} from '../config/appRegistry';

const STATIC_CATALOG_PATHS = new Set([
  ...OVERVIEW_NAV.map((i) => i.path),
  ...ADVANCED_TOOLS_NAV.map((i) => i.path),
  ...OPTIMIZATION_NAV_ITEMS.map((i) => i.path),
  ...SYSTEM_NAV.map((i) => i.path),
  ...Object.values(RESOURCE_PAGES).map((p) => p.path),
]);

const RESOURCE_PATHS = new Set(
  Object.values(RESOURCE_PAGES)
    .filter((p) => !p.hidden)
    .map((p) => p.path),
);

function buildPathSectionMap() {
  const map = new Map();

  OVERVIEW_NAV.forEach((item) => {
    map.set(item.path, ['section:overview']);
  });

  ADVANCED_NAV_GROUPS.forEach((group) => {
    group.items.forEach((item) => {
      map.set(item.path, ['section:advanced', `section:advanced:${group.id}`]);
    });
  });

  Object.values(RESOURCE_PAGES).forEach((page) => {
    if (page.hidden) return;
    const subgroup = page.navGroup;
    const sections = ['section:resources'];
    if (subgroup) sections.push(`section:resources:${subgroup}`);
    map.set(page.path, sections);
  });

  SYSTEM_NAV.forEach((item) => {
    map.set(item.path, ['section:system']);
  });

  return map;
}

const PATH_SECTIONS = buildPathSectionMap();

export function normalizeNavPath(path) {
  if (!path || path === '/') return '/';
  const base = path.split('?')[0];
  return base.endsWith('/') && base.length > 1 ? base.slice(0, -1) : base;
}

export function navSectionId(group, subgroup = null) {
  if (subgroup) return `section:${group}:${subgroup}`;
  return `section:${group}`;
}

export const NAV_ACCESS_GROUPS = [
  { id: 'overview', label: 'Overview' },
  { id: 'advanced', label: 'Advanced tools' },
  { id: 'resources', label: 'Resources' },
  { id: 'system', label: 'System' },
];

export const NAV_ACCESS_SUBGROUPS = {
  advanced: ADVANCED_NAV_GROUPS.map((group) => ({
    id: group.id,
    label: group.label,
    sectionId: navSectionId('advanced', group.id),
    parentSectionId: navSectionId('advanced'),
  })),
  resources: NAV_RESOURCE_GROUPS.map((group) => ({
    id: group.id,
    label: group.label,
    sectionId: navSectionId('resources', group.id),
    parentSectionId: navSectionId('resources'),
  })),
};

function sectionsAllowed(sections, allowed) {
  return sections.every((sectionId) => allowed.has(sectionId));
}

/**
 * @param {string} path
 * @param {string[]|undefined} allowedPaths from /auth/me or /settings/nav-access/me
 * @param {{ isSuperuser?: boolean }} options
 */
export function canViewNavPath(path, allowedPaths, { isSuperuser = false } = {}) {
  if (isSuperuser) return true;
  if (!allowedPaths?.length) return false;

  const allowed = new Set(allowedPaths);
  const normalized = normalizeNavPath(path);

  if (normalized.startsWith('section:')) {
    return allowed.has(normalized);
  }

  const sections = PATH_SECTIONS.get(normalized) || [];
  if (sections.length && !sectionsAllowed(sections, allowed)) return false;

  if (allowed.has(normalized)) return true;

  if (allowed.has('section:resources')) {
    if (RESOURCE_PATHS.has(normalized)) return true;
    if (!STATIC_CATALOG_PATHS.has(normalized) && normalized.startsWith('/')) {
      return true;
    }
  }

  return false;
}
