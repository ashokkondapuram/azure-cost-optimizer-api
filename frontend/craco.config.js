/** Suppress harmless source-map-loader warnings from autolinker (missing .ts sources in package). */
module.exports = {
  webpack: {
    configure: (webpackConfig) => {
      webpackConfig.ignoreWarnings = [
        ...(webpackConfig.ignoreWarnings || []),
        (warning) => {
          const resource = warning.module?.resource || warning.file || '';
          const message = String(warning.message || warning);
          return (
            /node_modules[/\\]autolinker/.test(resource)
            && /Failed to parse source map/.test(message)
          );
        },
      ];
      return webpackConfig;
    },
  },
};
