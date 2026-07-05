import api from './client';

export const fetchApiExplorerContext = () =>
  api.get('/admin/api-explorer/context').then((r) => r.data);

export const fetchOpenApiSpec = () =>
  api.get('/openapi.json').then((r) => r.data);
