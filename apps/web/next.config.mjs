/** @type {import('next').NextConfig} */

// Blurred appeal stills (PUB-02) are served from ONE public bucket only. The host comes from the
// project URL; without it no remote image is allowed at all.
let supabaseHost = null;
try { supabaseHost = new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "").hostname || null; } catch { supabaseHost = null; }

const nextConfig = {
  images: {
    remotePatterns: supabaseHost
      ? [{ protocol: "https", hostname: supabaseHost, pathname: "/storage/v1/object/public/appeal-public/**" }]
      : [],
  },
};

export default nextConfig;
