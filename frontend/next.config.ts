import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The /api/* proxy to the FastAPI backend lives in src/middleware.ts, not
  // here: a config rewrite cannot attach the Authorization header the backend
  // now requires. Two mechanisms on one path would race, so this stays empty.
  productionBrowserSourceMaps: false,
  experimental: {
    // Next.js aborts proxied requests after 30s by default, and the
    // src/middleware.ts rewrite is one. When the 7-day fundamentals
    // cache is stale, the first /api/screener or /api/signals call re-fetches
    // all ~156 tickers from Yahoo one by one (~100s measured), so the page
    // showed a 500 "socket hang up" even though the API finished fine.
    proxyTimeout: 300_000,
  },
  webpack(config) {
    config.module.rules.push({
      test: /\.svg$/,
      use: ["@svgr/webpack"],
    });
    return config;
  },
    
    turbopack: {
      rules: {
        '*.svg': {
          loaders: ['@svgr/webpack'],
          as: '*.js',
        },
      },
    },
  
};

export default nextConfig;
