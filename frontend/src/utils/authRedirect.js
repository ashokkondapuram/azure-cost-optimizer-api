/** Backend-only first path segments (not React routes). */
const BLOCKED_POST_LOGIN_ROOTS = new Set([
  'api',
  'health',
  'resources',
  'metrics',
  'optimize',
  'docs',
  'openapi.json',
  'redoc',
]);

function isSafePostLoginPath(path) {
  if (!path || !path.startsWith('/') || path.startsWith('//')) {
    return false;
  }
  const pathname = path.split(/[#?]/)[0];
  if (pathname === '/login' || pathname.startsWith('/login/')) {
    return false;
  }
  const first = pathname.split('/').filter(Boolean)[0];
  if (first && BLOCKED_POST_LOGIN_ROOTS.has(first)) {
    return false;
  }
  return true;
}

/** Resolve a safe in-app path after sign-in (query ?next= or router state). */
export function postLoginPath(searchParams, locationState) {
  const next = searchParams?.get?.('next');
  if (next && isSafePostLoginPath(next)) {
    return next;
  }

  const from = locationState?.from;
  if (from && typeof from === 'object' && from.pathname) {
    const path = `${from.pathname}${from.search || ''}${from.hash || ''}`;
    if (isSafePostLoginPath(path)) {
      return path;
    }
  }

  return '/';
}

export function loginPathWithNext(pathname, search = '') {
  const next = `${pathname}${search}`;
  if (!next || next === '/login') return '/login';
  return `/login?next=${encodeURIComponent(next)}`;
}
