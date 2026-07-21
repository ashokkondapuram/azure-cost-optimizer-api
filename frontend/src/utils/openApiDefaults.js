/** Prepare OpenAPI spec for the in-app explorer (ARM paths, app-side execution). */
export function withSubscriptionDefaults(spec, subscriptionId) {
  if (!spec || !subscriptionId) return spec;

  const next = structuredClone(spec);
  for (const pathItem of Object.values(next.paths || {})) {
    for (const operation of Object.values(pathItem)) {
      if (!operation || typeof operation !== 'object' || !Array.isArray(operation.parameters)) {
        continue;
      }
      for (const param of operation.parameters) {
        if (param.name === 'subscription_id' && param.in === 'query') {
          param.schema = { ...(param.schema || {}), default: subscriptionId };
          param.example = subscriptionId;
        }
        if (param.name === 'subscriptionId' && param.in === 'path') {
          param.schema = { ...(param.schema || {}), default: subscriptionId };
          param.example = subscriptionId;
        }
      }
    }
  }
  return next;
}

/** ARM paths with same-origin server so Try it out is proxied (not sent to Azure directly). */
export function prepareExplorerSpec(spec, subscriptionId) {
  if (!spec) return spec;
  const next = withSubscriptionDefaults(spec, subscriptionId);
  if (!next) return next;

  const prepared = structuredClone(next);
  prepared.servers = [
    {
      url: '',
      description: 'Proxied to https://management.azure.com (Azure token applied server-side)',
    },
  ];
  return prepared;
}
