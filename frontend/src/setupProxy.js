const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function (app) {
  // Only proxy actual API calls — never static assets
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:8000',
      changeOrigin: true,
      pathRewrite: { '^/api': '' },
      onError: (err, req, res) => {
        res.status(502).json({ error: 'Backend unavailable', detail: err.message });
      },
    })
  );
};
