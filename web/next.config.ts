import type { NextConfig } from "next";
import { loadEnvConfig } from "@next/env";
import path from "node:path";

// One env file for the whole repo: the root .env, shared with vision and the agent.
// (Next only reads its own folder by default.) Variables already in the shell win.
// forceReload: Next has already loaded this folder's env and would otherwise skip ours.
loadEnvConfig(path.resolve(__dirname, ".."), process.env.NODE_ENV !== "production", console, true);

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  transpilePackages: ["cues"],
  partialPrefetching: true,
  turbopack: {
    root: path.resolve(__dirname, ".."),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
