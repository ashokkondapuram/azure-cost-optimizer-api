const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function (app) {
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://127.0.0.1:8000',
      changeOrigin: true,
      pathRewrite: { '^/api': '' },
      onError: (_err, _req, res) => {
        res.status(502).json({ error: { message: 'Backend unavailable' } });
      },
    })
  );
};
