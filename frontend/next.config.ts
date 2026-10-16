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
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiTarget}/api/:path*` }];
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
