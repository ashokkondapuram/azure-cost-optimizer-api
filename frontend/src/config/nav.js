/** Sidebar nav group definitions — routes used for auto-expand on active page. */
export const NAV_GROUPS = {
  compute:     { label: 'Compute',     routes: ['/vms', '/disks'] },
  containers:  { label: 'Containers',  routes: ['/aks', '/acr'] },
  appservices: { label: 'App services', routes: ['/appservices'] },
  storage:     { label: 'Storage',     routes: ['/storage'] },
  networking:  { label: 'Networking',  routes: ['/publicips', '/loadbalancers', '/appgateways', '/nsgs'] },
  databases:   { label: 'Databases',   routes: ['/sql', '/cosmosdb', '/postgresql'] },
  security:    { label: 'Security',    routes: ['/keyvaults'] },
};

export const DEFAULT_NAV_OPEN = {
  compute: true,
  containers: false,
  appservices: false,
  storage: false,
  networking: false,
  databases: false,
  security: false,
};

export function groupForPath(pathname) {
  return Object.entries(NAV_GROUPS).find(([, g]) =>
    g.routes.some(r => pathname === r || pathname.startsWith(r + '/'))
  )?.[0] ?? null;
}
