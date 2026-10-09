"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { getSupabase } from "@/lib/supabase";
import { Brand } from "@/components/Shell";

export default function ResetPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const { error } = await getSupabase().auth.updateUser({ password });
    if (error) return setMsg({ ok: false, text: error.message });
    setMsg({ ok: true, text: "Passwort geändert. Weiterleitung …" });
    setTimeout(() => router.replace("/login"), 1200);
  }

  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <form onSubmit={submit} className="glass w-full max-w-sm space-y-3 rounded-3xl p-6">
        <div className="mb-4 flex justify-center"><Brand /></div>
        <h1 className="text-center text-xl font-semibold">Neues Passwort</h1>
        <input type="password" minLength={6} required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Neues Passwort"
          className="w-full rounded-xl border border-white/10 bg-secondary px-4 py-3 outline-none focus:border-primary" />
        <button className="w-full rounded-xl bg-primary py-3 font-semibold text-black active:scale-95">Speichern</button>
        {msg && <p className={`text-center text-sm ${msg.ok ? "text-emerald-400" : "text-red-400"}`}>{msg.text}</p>}
      </form>
    </main>
  );
}
