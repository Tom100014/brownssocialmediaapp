"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BUSINESS_TYPES, getSupabase, ROLE_HOME, type Role } from "@/lib/supabase";
import { Brand } from "@/components/Shell";

type Mode = "login" | "creator" | "partner";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [biz, setBiz] = useState({ name: "", type: "cafe", address: "", offer: "Gratis Getränk" });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    const m = new URLSearchParams(window.location.search).get("mode");
    if (m === "register") setMode("creator");
    if (m === "partner") setMode("partner");
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
      if (mode !== "login") {
        const meta =
          mode === "partner"
            ? { account_type: "partner", name, business_name: biz.name, business_type: biz.type, address: biz.address, offer: biz.offer }
            : { account_type: "influencer", name };
        const { data, error } = await sb.auth.signUp({
          email, password, options: { data: meta, emailRedirectTo: `${window.location.origin}/login` },
        });
        if (error) throw error;
        if (data.session && data.user) return await redirectByRole(data.user.id);
        setMsg({ ok: true, text: "Fast geschafft! Bitte bestätige deine E-Mail und logge dich dann ein." });
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

  async function forgot() {
    if (!email) return setMsg({ ok: false, text: "Bitte zuerst deine E-Mail eingeben." });
    const { error } = await getSupabase().auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/auth/reset` });
    setMsg(error ? { ok: false, text: error.message } : { ok: true, text: "Wir haben dir einen Link zum Zurücksetzen geschickt." });
  }

  const input = "w-full rounded-xl border border-white/10 bg-secondary px-4 py-3 outline-none focus:border-primary";
  const titles: Record<Mode, string> = { login: "Willkommen zurück", creator: "Black Card sichern", partner: "Partner werden" };

  return (
    <main className="grid min-h-dvh place-items-center px-4 py-8">
      <div className="glass w-full max-w-sm rounded-3xl p-6">
        <div className="mb-6 flex justify-center"><Brand /></div>
        <div className="mb-5 grid grid-cols-3 gap-1 rounded-xl bg-secondary p-1 text-xs">
          {(["login", "creator", "partner"] as Mode[]).map((m) => (
            <button key={m} type="button" onClick={() => { setMode(m); setMsg(null); }}
              className={`rounded-lg py-2 ${mode === m ? "bg-primary font-semibold text-black" : "text-white/70"}`}>
              {{ login: "Login", creator: "Creator", partner: "Café / Restaurant" }[m]}
            </button>
          ))}
        </div>
        <h1 className="mb-4 text-center text-xl font-semibold">{titles[mode]}</h1>
        <form onSubmit={submit} className="space-y-3">
          {mode !== "login" && <input className={input} placeholder={mode === "partner" ? "Dein Name" : "Name / @Handle"} value={name} onChange={(e) => setName(e.target.value)} required />}
          {mode === "partner" && (
            <>
              <input className={input} placeholder="Name des Betriebs" value={biz.name} onChange={(e) => setBiz({ ...biz, name: e.target.value })} required />
              <select className={input} value={biz.type} onChange={(e) => setBiz({ ...biz, type: e.target.value })}>
                {BUSINESS_TYPES.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}
              </select>
              <input className={input} placeholder="Adresse (Straße Nr., Nürnberg)" value={biz.address} onChange={(e) => setBiz({ ...biz, address: e.target.value })} required />
              <input className={input} placeholder="Angebot für Creator" value={biz.offer} onChange={(e) => setBiz({ ...biz, offer: e.target.value })} required />
            </>
          )}
          <input className={input} type="email" placeholder="E-Mail" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <input className={input} type="password" placeholder="Passwort" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} required />
          <button disabled={busy} className="w-full rounded-xl bg-primary py-3 font-semibold text-black active:scale-95 disabled:opacity-60">
            {busy ? "Bitte warten …" : mode === "login" ? "Einloggen" : "Registrieren"}
          </button>
        </form>
        {mode === "partner" && <p className="mt-3 text-center text-xs text-white/50">Dein Betrieb wird nach Prüfung durch uns freigeschaltet.</p>}
        {msg && <p className={`mt-4 text-center text-sm ${msg.ok ? "text-emerald-400" : "text-red-400"}`}>{msg.text}</p>}
        {mode === "login" && <button onClick={forgot} className="mt-4 w-full text-center text-sm text-primary">Passwort vergessen?</button>}
      </div>
    </main>
  );
}
