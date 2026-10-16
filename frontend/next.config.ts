import type { NextConfig } from "next";
import bundleAnalyzer from "@next/bundle-analyzer";

const withBundleAnalyzer = bundleAnalyzer({ enabled: process.env.ANALYZE === "true" });

// T043 adds the /api/* → FastAPI rewrite and image domains.
const nextConfig: NextConfig = {
  output: "standalone",
};

export default withBundleAnalyzer(nextConfig);
