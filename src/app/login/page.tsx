"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSupabase, ROLE_HOME, type Role } from "@/lib/supabase";
import { Brand } from "@/components/Shell";

export default function LoginPage() {
  const router = useRouter();
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    setRegister(new URLSearchParams(window.location.search).get("mode") === "register");
  }, []);

  async function redirectByRole(userId: string) {
    const { data } = await getSupabase().from("profiles").select("role,is_banned").eq("id", userId).single();
    if (!data) return setMsg({ ok: false, text: "Kein Profil gefunden." });
    if (data.is_banned) {
      await getSupabase().auth.signOut();
      return setMsg({ ok: false, text: "Dieser Account wurde gesperrt." });
    }
    router.replace(ROLE_HOME[data.role as Role] ?? "/dashboard");
  }

  useEffect(() => {
    getSupabase().auth.getUser().then(({ data }) => {
      if (data.user) redirectByRole(data.user.id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const sb = getSupabase();
    try {
      if (register) {
        const { data, error } = await sb.auth.signUp({ email, password, options: { data: { name } } });
        if (error) throw error;
        if (data.session && data.user) return await redirectByRole(data.user.id);
        setMsg({ ok: true, text: "Fast geschafft! Bitte bestätige deine E-Mail und logge dich ein." });
      } else {
        const { data, error } = await sb.auth.signInWithPassword({ email, password });
        if (error) throw error;
        await redirectByRole(data.user.id);
      }
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "Anmeldung fehlgeschlagen." });
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded-xl border border-white/10 bg-secondary px-4 py-3 outline-none focus:border-primary";

  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <div className="glass w-full max-w-sm rounded-3xl p-6">
        <div className="mb-6 flex justify-center"><Brand /></div>
        <h1 className="mb-1 text-center text-xl font-semibold">{register ? "Black Card sichern" : "Willkommen zurück"}</h1>
        <p className="mb-5 text-center text-sm text-white/55">Admins, Partner und Creator melden sich hier an.</p>
        <form onSubmit={submit} className="space-y-3">
          {register && <input className={input} placeholder="Name / @Handle" value={name} onChange={(e) => setName(e.target.value)} required />}
          <input className={input} type="email" placeholder="E-Mail" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <input className={input} type="password" placeholder="Passwort" autoComplete={register ? "new-password" : "current-password"} minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} required />
          <button disabled={busy} className="w-full rounded-xl bg-primary py-3 font-semibold text-black active:scale-95 disabled:opacity-60">
            {busy ? "Bitte warten …" : register ? "Registrieren" : "Einloggen"}
          </button>
        </form>
        {msg && <p className={`mt-4 text-center text-sm ${msg.ok ? "text-emerald-400" : "text-red-400"}`}>{msg.text}</p>}
        <button onClick={() => setRegister(!register)} className="mt-5 w-full text-center text-sm text-primary">
          {register ? "Bereits Mitglied? Einloggen" : "Noch keinen Pass? Registrieren"}
        </button>
      </div>
    </main>
  );
}
