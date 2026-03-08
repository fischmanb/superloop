import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Native modules that should not be bundled for server components
  serverExternalPackages: ["better-sqlite3", "duckdb"],
  // Fix workspace root detection in monorepo
  outputFileTracingRoot: path.join(__dirname, "../../"),
};

export default nextConfig;
