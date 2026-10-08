import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (!client) {
    client = createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://placeholder.supabase.co",
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "placeholder-anon-key",
    );
  }
  return client;
}

export type Role = "admin" | "partner" | "influencer";

export interface Profile {
  id: string;
  role: Role;
  name: string | null;
  trust_score: number;
  is_banned: boolean;
}

export const ROLE_HOME: Record<Role, string> = {
  admin: "/admin",
  partner: "/partner/scanner",
  influencer: "/dashboard",
};

export const PASS_PREFIX = "BCP:";
