"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSupabase, ROLE_HOME, type Profile, type Role } from "./supabase";

/** Loads the signed-in profile; redirects to /login or to the role's home if the role doesn't match. */
export function useProfile(required: Role) {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      const sb = getSupabase();
      const { data: auth } = await sb.auth.getUser();
      if (!auth.user) return router.replace("/login");
      const { data } = await sb.from("profiles").select("*").eq("id", auth.user.id).single();
      if (!active) return;
      if (!data) return router.replace("/login");
      const p = data as Profile;
      if (p.role !== required && p.role !== "admin") return router.replace(ROLE_HOME[p.role]);
      setProfile(p);
    })();
    return () => {
      active = false;
    };
  }, [router, required]);

  return profile;
}

export async function signOut() {
  await getSupabase().auth.signOut();
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full reload clears client state
  window.location.assign("/login");
}
