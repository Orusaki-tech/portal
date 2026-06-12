import type { NextConfig } from "next"

const API_URL = process.env.API_URL || "http://localhost:8000"
const TITILER_URL = process.env.TITILER_URL || "https://realitysync-titiler-36pbu2hrsq-uc.a.run.app"

const nextConfig: NextConfig = {
  output: process.env.NODE_ENV === "production" ? "standalone" : undefined,

  poweredByHeader: false,

  compiler: {
    removeConsole: process.env.NODE_ENV === "production",
  },

  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ]
  },

  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_URL}/api/:path*`,
      },
      {
        source: "/tiles/:path*",
        destination: `${API_URL}/tiles/:path*`,
      },
      {
        source: "/upload/:path*",
        destination: `${API_URL}/upload/:path*`,
      },
      {
        source: "/cog/:path*",
        destination: `${TITILER_URL}/cog/:path*`,
      },
    ]
  },
}

export default nextConfig
