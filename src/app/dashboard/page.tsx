"use client";

import { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import { Link2, Lock, ShieldCheck, Unlock } from "lucide-react";
import { getSupabase, PASS_PREFIX } from "@/lib/supabase";
import { signOut, useProfile } from "@/lib/useProfile";
import { Header, Loading } from "@/components/Shell";

interface Pass {
  pass_token: string;
  status: "active" | "locked" | "revoked";
  cooldown_until: string | null;
}

function fmt(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const d = Math.floor(s / 86400);
  const h = String(Math.floor((s % 86400) / 3600)).padStart(2, "0");
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const sec = String(s % 60).padStart(2, "0");
  return `${d > 0 ? `${d}d ` : ""}${h}:${m}:${sec}`;
}

export default function Dashboard() {
  const profile = useProfile("influencer");
  const [pass, setPass] = useState<Pass | null>(null);
  const [qr, setQr] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const [story, setStory] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    const { data } = await getSupabase().from("creator_passes").select("pass_token,status,cooldown_until").maybeSingle();
    if (data) setPass(data as Pass);
  }, []);

  useEffect(() => {
    if (profile) load();
  }, [profile, load]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!pass) return;
    QRCode.toDataURL(PASS_PREFIX + pass.pass_token, {
      width: 480, margin: 1, color: { dark: "#0A0A0A", light: "#F2D675" },
    }).then(setQr);
  }, [pass]);

  async function submitStory(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const { data, error } = await getSupabase().rpc("submit_story", { p_url: story.trim() });
    setBusy(false);
    if (error || !data?.ok) return setMsg({ ok: false, text: error?.message ?? data?.reason ?? "Fehler" });
    setStory("");
    setMsg({ ok: true, text: "Story eingereicht – dein Pass ist entsperrt." });
    load();
  }

  if (!profile || !pass) return <Loading />;

  const remaining = pass.cooldown_until ? new Date(pass.cooldown_until).getTime() - now : 0;
  const cooling = remaining > 0;
  const awaitingStory = pass.status === "locked";
  const revoked = pass.status === "revoked" || profile.is_banned;
  const usable = !revoked && !awaitingStory && !cooling;

  return (
    <main className="pb-16">
      <Header title={`Creator · ${profile.name ?? ""}`} onSignOut={signOut} />
      <div className="mx-auto max-w-md space-y-5 px-4">
        <section className="glass rounded-3xl p-6 text-center shadow-[0_0_60px_rgba(212,175,55,0.12)]">
          <p className="text-xs uppercase tracking-[0.3em] text-primary">Black Card</p>
          <div className="relative mx-auto mt-4 w-64 max-w-full overflow-hidden rounded-2xl">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {qr && <img src={qr} alt="Dein Pass QR-Code" className={`w-full ${usable ? "" : "opacity-20 blur-[2px]"}`} />}
            {!usable && <Lock className="absolute inset-0 m-auto h-14 w-14 text-primary" />}
          </div>
          <p className={`mt-4 flex items-center justify-center gap-2 font-medium ${usable ? "text-emerald-400" : "text-red-400"}`}>
            {usable ? <Unlock className="h-4 w-4" /> : <Lock className="h-4 w-4" />}
            {revoked ? "Pass gesperrt" : awaitingStory ? "Story-Link benötigt" : cooling ? "Cooldown aktiv" : "Bereit zum Einlösen"}
          </p>
          {cooling && (
            <p className="mt-2 font-mono text-3xl tracking-wider text-primary" aria-live="off">{fmt(remaining)}</p>
          )}
          <p className="mt-3 flex items-center justify-center gap-1.5 text-xs text-white/50">
            <ShieldCheck className="h-3.5 w-3.5" /> Trust-Score {profile.trust_score}/100
          </p>
        </section>

        {awaitingStory && !revoked && (
          <form onSubmit={submitStory} className="glass space-y-3 rounded-3xl p-5">
            <p className="font-semibold">Story-Link einreichen</p>
            <p className="text-sm text-white/55">Poste deine Story, füge den Link ein und entsperre deinen Pass.</p>
            <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-secondary px-3">
              <Link2 className="h-4 w-4 text-primary" />
              <input
                type="url" required placeholder="https://instagram.com/stories/…"
                value={story} onChange={(e) => setStory(e.target.value)}
                className="w-full bg-transparent py-3 outline-none"
              />
            </div>
            <button disabled={busy} className="w-full rounded-xl bg-primary py-3 font-semibold text-black active:scale-95 disabled:opacity-60">
              {busy ? "Prüfe …" : "Pass entsperren"}
            </button>
          </form>
        )}
        {msg && <p className={`text-center text-sm ${msg.ok ? "text-emerald-400" : "text-red-400"}`}>{msg.text}</p>}
      </div>
    </main>
  );
}
