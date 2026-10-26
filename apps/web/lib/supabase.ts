import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Browser/server Supabase client using only the public URL and anon key.
 * The anon role has no table access; public data comes from narrow RPCs
 * (engg/docs/DECISIONS.md D-003). Returns null until the project is configured.
 */
export function getSupabase(): SupabaseClient | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return null;
  return createClient(url, key, { auth: { persistSession: typeof window !== "undefined" } });
}
