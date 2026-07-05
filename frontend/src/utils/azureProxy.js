/** Rewrite Swagger Try it out requests to the app proxy (never call Azure from the browser). */

const MANAGEMENT_HOST = 'management.azure.com';

function compileRoutes(routes = []) {
  return routes.map((route) => ({
    ...route,
    pattern: new RegExp(route.arm, 'i'),
  }));
}

function fillTemplate(template, groups) {
  return template.replace(/\{(\w+)\}/g, (_, key) => encodeURIComponent(groups[key] ?? ''));
}

function buildProxyUrl(route, groups, searchParams) {
  let path = fillTemplate(route.proxy, groups);
  const query = new URLSearchParams();

  if (route.query) {
    Object.entries(route.query).forEach(([key, template]) => {
      query.set(key, fillTemplate(template, groups));
    });
  }

  if (route.forwardQuery) {
    route.forwardQuery.forEach((name) => {
      const value = searchParams.get(name);
      if (value != null && value !== '') {
        const proxyName = name === 'metricnames' ? 'metric_names' : name;
        query.set(proxyName, value);
      }
    });
  }

  const qs = query.toString();
  return qs ? `${path}?${qs}` : path;
}

function normalizeArmPath(pathname) {
  return pathname.replace(/\/resourceGroups\//gi, '/resourcegroups/');
}

function matchProxyRoute(pathname, routes) {
  const normalized = normalizeArmPath(pathname);
  for (const route of routes) {
    const match = normalized.match(route.pattern);
    if (match) {
      return { route, groups: match.groups || {} };
    }
  }
  return null;
}

function isAzureManagementRequest(url, proxyConfig) {
  const host = (proxyConfig?.managementHost || MANAGEMENT_HOST).toLowerCase();
  if (url.hostname.toLowerCase() === host) return true;
  return url.pathname.startsWith('/subscriptions')
    || /^\/[^/]+\/providers\/Microsoft\.Insights\/metrics$/i.test(url.pathname);
}

export function rewriteAzureRequestToAppProxy(request, proxyConfig) {
  if (!request?.url || !proxyConfig?.routes?.length) return request;

  try {
    const url = new URL(request.url, window.location.origin);
    if (!isAzureManagementRequest(url, proxyConfig)) return request;

    const routes = compileRoutes(proxyConfig.routes);
    const hit = matchProxyRoute(url.pathname, routes);
    if (!hit) {
      return request;
    }

    let proxyUrl = buildProxyUrl(hit.route, hit.groups, url.searchParams);

    if (proxyUrl.includes('/api/azure/resources')) {
      const proxy = new URL(proxyUrl, window.location.origin);
      const filter = url.searchParams.get('$filter') || '';
      const typeMatch = /resourceType eq '([^']+)'/i.exec(filter);
      if (typeMatch) {
        proxy.searchParams.set('arm_type', typeMatch[1]);
      }
      proxyUrl = `${proxy.pathname}${proxy.search}`;
    }

    request.url = proxyUrl;
  } catch {
    // Leave request unchanged if URL parsing fails.
  }

  // Safety: the browser must never call management.azure.com with the app JWT.
  if (typeof request.url === 'string' && request.url.includes(MANAGEMENT_HOST)) {
    try {
      const azureUrl = new URL(request.url);
      const routes = compileRoutes(proxyConfig.routes);
      const hit = matchProxyRoute(azureUrl.pathname, routes);
      if (hit) {
        request.url = buildProxyUrl(hit.route, hit.groups, azureUrl.searchParams);
      }
    } catch {
      // ignore
    }
  }

  return request;
}

export function createAzureProxyInterceptor(proxyConfig, { getSessionToken, subscriptionId } = {}) {
  return (request) => {
    rewriteAzureRequestToAppProxy(request, proxyConfig);

    const sessionToken = typeof getSessionToken === 'function' ? getSessionToken() : null;
    if (sessionToken) {
      request.headers.Authorization = `Bearer ${sessionToken}`;
    }

    if (subscriptionId && request.url) {
      try {
        const url = new URL(request.url, window.location.origin);
        if (!url.searchParams.has('subscription_id')
            && (url.pathname.startsWith('/api/azure/') || url.pathname.startsWith('/api/costs'))) {
          url.searchParams.set('subscription_id', subscriptionId);
          request.url = `${url.pathname}${url.search}`;
        }
      } catch {
        // ignore
      }
    }

    return request;
  };
}
