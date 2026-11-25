/**
 * Static export for GitHub Pages.
 *
 *   NEXT_PUBLIC_BASE_PATH=/TrainerHub npm run build
 *
 * Locally the base path is empty, so `npm run dev` serves from "/".
 */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  basePath,
  assetPrefix: basePath || undefined,
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
};

export default nextConfig;
