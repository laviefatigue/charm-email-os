import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable standalone output for Docker deployment
  output: "standalone",

  // Environment variables accessible in browser
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://ccssgc4gowsog04wck400o0w.31.97.142.123.sslip.io",
  },
};

export default nextConfig;
