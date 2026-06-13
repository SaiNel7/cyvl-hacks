import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["deck.gl", "@deck.gl"],
};

export default nextConfig;
