"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Ban, Flag, Plus, Search } from "lucide-react";
import { getSupabase, type Profile } from "@/lib/supabase";
import { signOut, useProfile } from "@/lib/useProfile";
import { Header, Loading } from "@/components/Shell";

interface Partner { id: string; name: string; owner_id: string | null; active: boolean }
interface Redemption {
  id: string; partner_id: string; influencer_id: string;
  status: string; story_url: string | null; redeemed_at: string;
}

type Tab = "partners" | "creators" | "redemptions";

export default function Admin() {
  const me = useProfile("admin");
  const [tab, setTab] = useState<Tab>("partners");
  const [partners, setPartners] = useState<Partner[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [reds, setReds] = useState<Redemption[]>([]);
  const [q, setQ] = useState("");
  const [newName, setNewName] = useState("");
  const [newOwner, setNewOwner] = useState("");
  const [err, setErr] = useState("");
  const [dayAgo, setDayAgo] = useState(0);

  const load = useCallback(async () => {
    const sb = getSupabase();
    const [p, pr, r] = await Promise.all([
      sb.from("partners").select("*").order("name"),
      sb.from("profiles").select("*").order("trust_score"),
      sb.from("redemptions").select("*").order("redeemed_at", { ascending: false }).limit(200),
    ]);
    setPartners((p.data ?? []) as Partner[]);
    setProfiles((pr.data ?? []) as Profile[]);
    setReds((r.data ?? []) as Redemption[]);
    setDayAgo(Date.now() - 864e5);
  }, []);

  useEffect(() => {
    if (me) load();
  }, [me, load]);

  async function run(op: PromiseLike<{ error: { message: string } | null }>) {
    const { error } = await op;
    setErr(error?.message ?? "");
    load();
  }

  const names = useMemo(() => new Map(profiles.map((p) => [p.id, p.name ?? p.id.slice(0, 8)])), [profiles]);
  const partnerNames = useMemo(() => new Map(partners.map((p) => [p.id, p.name])), [partners]);
  const needle = q.trim().toLowerCase();
  const partnerOwners = profiles.filter((p) => p.role === "partner");

  const flaggedCount = reds.filter((r) => r.status === "flagged").length;
  const lowTrust = profiles.filter((p) => p.role === "influencer" && p.trust_score < 30 && !p.is_banned).length;

  // Mehrfach-Einlösungen binnen 24h = Betrugsverdacht
  const suspicious = useMemo(() => {
    const byCreator = new Map<string, number>();
    reds.filter((r) => new Date(r.redeemed_at).getTime() > dayAgo).forEach((r) => byCreator.set(r.influencer_id, (byCreator.get(r.influencer_id) ?? 0) + 1));
    return new Set([...byCreator].filter(([, n]) => n > 1).map(([id]) => id));
  }, [reds, dayAgo]);

  if (!me) return <Loading />;

  const card = "glass rounded-2xl p-4";
  const btn = "rounded-lg border border-white/10 px-3 py-1.5 text-xs active:scale-95";

  return (
    <main className="pb-16">
      <Header title="Admin Control" onSignOut={signOut} />
      <div className="mx-auto max-w-5xl space-y-4 px-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ["Partner", partners.length], ["Creator", profiles.filter((p) => p.role === "influencer").length],
            ["Verdächtig", suspicious.size + flaggedCount], ["Trust < 30", lowTrust],
          ].map(([l, v]) => (
            <div key={l} className={card}><p className="text-xs text-white/50">{l}</p><p className="gold-text text-3xl font-bold">{v}</p></div>
          ))}
        </div>

        <div className="flex gap-2 overflow-x-auto">
          {(["partners", "creators", "redemptions"] as Tab[]).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`rounded-full px-4 py-2 text-sm capitalize ${tab === t ? "bg-primary text-black" : "glass"}`}>
              {{ partners: "Partner", creators: "Creator & Trust", redemptions: "Einlösungen" }[t]}
            </button>
          ))}
        </div>

        <div className="glass flex items-center gap-2 rounded-xl px-3">
          <Search className="h-4 w-4 text-primary" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Suchen …" className="w-full bg-transparent py-2.5 outline-none" />
        </div>
        {err && <p className="text-sm text-red-400">{err}</p>}

        {tab === "partners" && (
          <section className="space-y-2">
            <form
              className={`${card} flex flex-col gap-2 sm:flex-row`}
              onSubmit={(e) => {
                e.preventDefault();
                run(getSupabase().from("partners").insert({ name: newName.trim(), owner_id: newOwner || null }));
                setNewName(""); setNewOwner("");
              }}
            >
              <input required value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Neuer Partner (Name)" className="flex-1 rounded-lg bg-secondary px-3 py-2 outline-none" />
              <select value={newOwner} onChange={(e) => setNewOwner(e.target.value)} className="rounded-lg bg-secondary px-3 py-2">
                <option value="">Inhaber wählen …</option>
                {partnerOwners.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
              <button className="flex items-center justify-center gap-1 rounded-lg bg-primary px-4 py-2 font-semibold text-black"><Plus className="h-4 w-4" /> Anlegen</button>
            </form>
            {partners.filter((p) => p.name.toLowerCase().includes(needle)).map((p) => (
              <div key={p.id} className={`${card} flex items-center justify-between gap-3`}>
                <div className="min-w-0">
                  <p className="truncate font-medium">{p.name}</p>
                  <p className="text-xs text-white/50">Inhaber: {p.owner_id ? names.get(p.owner_id) ?? "–" : "–"}</p>
                </div>
                <button onClick={() => run(getSupabase().from("partners").update({ active: !p.active }).eq("id", p.id))}
                  className={`${btn} ${p.active ? "text-emerald-400" : "text-red-400"}`}>{p.active ? "Aktiv" : "Inaktiv"}</button>
              </div>
            ))}
          </section>
        )}

        {tab === "creators" && (
          <section className="space-y-2">
            {profiles.filter((p) => p.role === "influencer" && (p.name ?? "").toLowerCase().includes(needle)).map((p) => (
              <div key={p.id} className={`${card} flex flex-wrap items-center justify-between gap-3`}>
                <div>
                  <p className="font-medium">{p.name} {suspicious.has(p.id) && <span className="ml-1 rounded bg-red-500/20 px-1.5 text-xs text-red-400">Mehrfach-Scan 24h</span>}</p>
                  <p className="text-xs text-white/50">{p.is_banned ? "Gesperrt" : "Aktiv"}</p>
                </div>
                <div className="flex items-center gap-2">
                  <button className={btn} onClick={() => run(getSupabase().from("profiles").update({ trust_score: Math.max(0, p.trust_score - 10) }).eq("id", p.id))}>−10</button>
                  <span className={`w-12 text-center font-mono text-lg ${p.trust_score < 30 ? "text-red-400" : "text-primary"}`}>{p.trust_score}</span>
                  <button className={btn} onClick={() => run(getSupabase().from("profiles").update({ trust_score: Math.min(100, p.trust_score + 10) }).eq("id", p.id))}>+10</button>
                  <button onClick={() => run(getSupabase().from("profiles").update({ is_banned: !p.is_banned }).eq("id", p.id))}
                    className={`${btn} flex items-center gap-1 ${p.is_banned ? "text-emerald-400" : "text-red-400"}`}>
                    <Ban className="h-3.5 w-3.5" /> {p.is_banned ? "Entsperren" : "Bannen"}
                  </button>
                </div>
              </div>
            ))}
          </section>
        )}

        {tab === "redemptions" && (
          <section className="space-y-2">
            {reds.filter((r) => `${names.get(r.influencer_id)} ${partnerNames.get(r.partner_id)}`.toLowerCase().includes(needle)).map((r) => (
              <div key={r.id} className={`${card} flex flex-wrap items-center justify-between gap-3`}>
                <div className="min-w-0">
                  <p className="font-medium">{names.get(r.influencer_id) ?? "?"} → {partnerNames.get(r.partner_id) ?? "?"}</p>
                  <p className="text-xs text-white/50">{new Date(r.redeemed_at).toLocaleString("de-DE")} · {r.status}</p>
                  {r.story_url && <a href={r.story_url} target="_blank" rel="noopener noreferrer" className="block max-w-xs truncate text-xs text-primary underline">{r.story_url}</a>}
                </div>
                <button onClick={() => run(getSupabase().from("redemptions").update({ status: r.status === "flagged" ? "pending" : "flagged" }).eq("id", r.id))}
                  className={`${btn} flex items-center gap-1 ${r.status === "flagged" ? "text-red-400" : ""}`}>
                  <Flag className="h-3.5 w-3.5" /> {r.status === "flagged" ? "Markierung entfernen" : "Als Betrug markieren"}
                </button>
              </div>
            ))}
          </section>
        )}
      </div>
    </main>
  );
}
