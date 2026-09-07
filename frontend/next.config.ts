import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit .next/standalone for a small production Docker image.
  output: "standalone",
};

export default nextConfig;
