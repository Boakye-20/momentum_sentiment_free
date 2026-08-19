import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The /api/* proxy to the FastAPI backend lives in src/middleware.ts, not
  // here: a config rewrite cannot attach the Authorization header the backend
  // now requires. Two mechanisms on one path would race, so this stays empty.
  productionBrowserSourceMaps: false,
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
