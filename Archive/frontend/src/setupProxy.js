const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function (app) {
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:8000',
      changeOrigin: true,
      pathRewrite: { '^/api': '' },
      onError: (_err, _req, res) => {
        res.status(502).json({ error: 'Backend unavailable' });
      },
    })
  );
};
