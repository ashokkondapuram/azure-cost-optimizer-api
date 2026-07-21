const { createProxyMiddleware } = require('http-proxy-middleware');

const gatewayTarget =
  process.env.GATEWAY_PROXY_TARGET || 'http://gateway:8080';

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
