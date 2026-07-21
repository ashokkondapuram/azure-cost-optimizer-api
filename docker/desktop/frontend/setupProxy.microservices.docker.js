const { createProxyMiddleware } = require('http-proxy-middleware');

/**
 * Microservices dev proxy — routes API traffic through the platform gateway.
 * The gateway fans out to core, cost, analysis, inventory, and metrics services.
 *
 * Set BACKEND_PROXY_TARGET=http://gateway:8080 when COMPOSE_PROFILES includes microservices.
 */
const gatewayTarget =
  process.env.GATEWAY_PROXY_TARGET ||
  process.env.BACKEND_PROXY_TARGET ||
  'http://gateway:8080';

module.exports = function (app) {
  app.use(
    '/api',
    createProxyMiddleware({
      target: gatewayTarget,
      changeOrigin: true,
      pathRewrite: { '^/api': '' },
      timeout: 60_000,
      proxyTimeout: 60_000,
      onError: (_err, _req, res) => {
        res.status(502).json({ error: { message: 'API gateway unavailable' } });
      },
    })
  );
};
