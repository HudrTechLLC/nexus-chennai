/** @type {import('next').NextConfig} */

// Blurred appeal stills (PUB-02) are served from ONE public bucket only. The host comes from the
// project URL; without it no remote image is allowed at all.
let supabaseHost = null;
try { supabaseHost = new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "").hostname || null; } catch { supabaseHost = null; }

// Short paths people type or see in the deck. Temporary (307), so browsers never cache them for good.
export const REDIRECTS = [
  { source: "/login", destination: "/console/login", permanent: false },
];

const nextConfig = {
  async redirects() {
    return REDIRECTS;
  },
  images: {
    remotePatterns: supabaseHost
      ? [{ protocol: "https", hostname: supabaseHost, pathname: "/storage/v1/object/public/appeal-public/**" }]
      : [],
  },
};

export default nextConfig;
