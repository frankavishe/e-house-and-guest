import type { NextConfig } from "next";
import bundleAnalyzer from "@next/bundle-analyzer";
import createNextIntlPlugin from "next-intl/plugin";

const withBundleAnalyzer = bundleAnalyzer({ enabled: process.env.ANALYZE === "true" });
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

// Server-side target of the /api/* proxy. The browser only ever talks to this origin
// (same-origin cookies, no CORS; research.md R10).
const apiTarget = (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");

// Listing photos come from the public bucket (MinIO locally, S3/R2 in production).
const publicMedia = new URL(process.env.S3_PUBLIC_BASE_URL ?? "http://localhost:9000/public");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  experimental: {
    // The whole stylesheet is ~6 KB gz. Inlining it saves the render-blocking CSS request,
    // one full round trip before first paint on slow 3G (Principle VI, frontend/perf-report.md).
    inlineCss: true,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiTarget}/api/:path*` }];
  },
  webpack(config, { dev }) {
    // Playwright writes traces under the bind-mounted project while e2e runs; watching them
    // makes `next dev` recompile and full-reload pages mid-test.
    if (dev) {
      config.watchOptions = {
        ...config.watchOptions,
        ignored: [
          "**/.git/**",
          "**/node_modules/**",
          "**/.next/**",
          "**/test-results/**",
          "**/playwright-report/**",
        ],
      };
    }
    return config;
  },
  images: {
    remotePatterns: [
      {
        protocol: publicMedia.protocol.replace(":", "") as "http" | "https",
        hostname: publicMedia.hostname,
        port: publicMedia.port,
        pathname: `${publicMedia.pathname.replace(/\/$/, "")}/**`,
      },
    ],
  },
};

export default withBundleAnalyzer(withNextIntl(nextConfig));
