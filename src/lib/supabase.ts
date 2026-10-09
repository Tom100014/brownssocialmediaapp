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
  partner: "/partner",
  influencer: "/dashboard",
};

export const PASS_PREFIX = "BCP:";

export const BUSINESS_TYPES = [
  { value: "cafe", label: "Café" },
  { value: "restaurant", label: "Restaurant" },
  { value: "bar", label: "Bar" },
  { value: "lounge", label: "Lounge" },
  { value: "bakery", label: "Bäckerei" },
  { value: "other", label: "Sonstiges" },
] as const;

export interface Partner {
  id: string;
  name: string;
  owner_id: string | null;
  active: boolean;
  type: string;
  address: string | null;
  lat: number | null;
  lng: number | null;
  offer: string;
}

/** Geocode an address in Nürnberg via OpenStreetMap Nominatim (client-side, best effort). */
export async function geocode(address: string): Promise<{ lat: number; lng: number } | null> {
  try {
    const q = encodeURIComponent(/n(ü|ue)rnberg/i.test(address) ? address : `${address}, Nürnberg`);
    const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${q}`);
    const j = (await res.json()) as { lat: string; lon: string }[];
    return j[0] ? { lat: parseFloat(j[0].lat), lng: parseFloat(j[0].lon) } : null;
  } catch {
    return null;
  }
}
