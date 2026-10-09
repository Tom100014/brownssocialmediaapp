"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Ban, Check, Flag, RotateCcw, Search } from "lucide-react";
import { BUSINESS_TYPES, geocode, getSupabase, type Partner, type Profile, type Role } from "@/lib/supabase";
import { signOut, useProfile } from "@/lib/useProfile";
import { Header, Loading } from "@/components/Shell";

interface Redemption {
  id: string; partner_id: string; influencer_id: string;
  status: string; story_url: string | null; redeemed_at: string;
}
interface Pass { influencer_id: string; status: string; cooldown_until: string | null }
type Tab = "partners" | "users" | "redemptions" | "settings";

const SETTINGS: { key: string; label: string; hint: string }[] = [
  { key: "cooldown_days", label: "Cooldown (Tage)", hint: "Wartezeit zwischen zwei Einlösungen" },
  { key: "min_trust_score", label: "Mindest-Trust-Score", hint: "Darunter keine Einlösung mehr" },
  { key: "trust_verified", label: "Trust-Bonus bei geprüfter Story", hint: "Punkte" },
  { key: "trust_flagged", label: "Trust-Abzug bei Betrug", hint: "Punkte" },
];

export default function Admin() {
  const me = useProfile("admin");
  const [tab, setTab] = useState<Tab>("partners");
  const [partners, setPartners] = useState<Partner[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [passes, setPasses] = useState<Pass[]>([]);
  const [reds, setReds] = useState<Redemption[]>([]);
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  const [dayAgo, setDayAgo] = useState(0);
  const [edit, setEdit] = useState<Partner | null>(null);

  const load = useCallback(async () => {
    const sb = getSupabase();
    const [p, pr, r, ps, st] = await Promise.all([
      sb.from("partners").select("*").order("created_at", { ascending: false }),
      sb.from("profiles").select("*").order("created_at", { ascending: false }),
      sb.from("redemptions").select("*").order("redeemed_at", { ascending: false }).limit(300),
      sb.from("creator_passes").select("influencer_id,status,cooldown_until"),
      sb.from("app_settings").select("*"),
    ]);
    setPartners((p.data ?? []) as Partner[]);
    setProfiles((pr.data ?? []) as Profile[]);
    setReds((r.data ?? []) as Redemption[]);
    setPasses((ps.data ?? []) as Pass[]);
    setSettings(Object.fromEntries(((st.data ?? []) as { key: string; value: string }[]).map((x) => [x.key, x.value])));
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
  async function review(id: string, verdict: "verified" | "flagged") {
    const { data, error } = await getSupabase().rpc("review_redemption", { p_id: id, p_verdict: verdict });
    setErr(error?.message ?? (data && !data.ok ? data.reason : ""));
    load();
  }

  const names = useMemo(() => new Map(profiles.map((p) => [p.id, p.name ?? p.id.slice(0, 8)])), [profiles]);
  const partnerNames = useMemo(() => new Map(partners.map((p) => [p.id, p.name])), [partners]);
  const passOf = useMemo(() => new Map(passes.map((p) => [p.influencer_id, p])), [passes]);
  const needle = q.trim().toLowerCase();
  const owners = profiles.filter((p) => p.role === "partner");

  const suspicious = useMemo(() => {
    const byCreator = new Map<string, number>();
    reds.filter((r) => new Date(r.redeemed_at).getTime() > dayAgo).forEach((r) => byCreator.set(r.influencer_id, (byCreator.get(r.influencer_id) ?? 0) + 1));
    return new Set([...byCreator].filter(([, n]) => n > 1).map(([id]) => id));
  }, [reds, dayAgo]);

  if (!me) return <Loading />;

  const pending = partners.filter((p) => !p.active);
  const toReview = reds.filter((r) => r.status === "story_submitted").length;
  const card = "glass rounded-2xl p-4";
  const btn = "rounded-lg border border-white/10 px-3 py-1.5 text-xs active:scale-95";
  const field = "rounded-lg border border-white/10 bg-secondary px-3 py-2 outline-none focus:border-primary";

  async function savePartner(e: React.FormEvent) {
    e.preventDefault();
    if (!edit) return;
    const old = partners.find((p) => p.id === edit.id);
    const geo = !old || old.address !== edit.address || edit.lat == null ? await geocode(edit.address ?? "") : { lat: edit.lat, lng: edit.lng };
    await run(getSupabase().from("partners").update({
      name: edit.name, type: edit.type, address: edit.address, offer: edit.offer, owner_id: edit.owner_id,
      lat: geo?.lat ?? null, lng: geo?.lng ?? null,
    }).eq("id", edit.id));
    setEdit(null);
  }

  return (
    <main className="pb-16">
      <Header title="Admin Control" onSignOut={signOut} />
      <div className="mx-auto max-w-5xl space-y-4 px-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {([
            ["Zur Freigabe", pending.length], ["Aktive Partner", partners.length - pending.length],
            ["Stories prüfen", toReview], ["Verdächtig", suspicious.size],
          ] as [string, number][]).map(([l, v]) => (
            <div key={l} className={card}><p className="text-xs text-white/50">{l}</p><p className="gold-text text-3xl font-bold">{v}</p></div>
          ))}
        </div>

        <div className="flex gap-2 overflow-x-auto">
          {([["partners", "Partner"], ["users", "Nutzer & Trust"], ["redemptions", "Einlösungen"], ["settings", "Einstellungen"]] as [Tab, string][]).map(([t, l]) => (
            <button key={t} onClick={() => setTab(t)} className={`shrink-0 rounded-full px-4 py-2 text-sm ${tab === t ? "bg-primary text-black" : "glass"}`}>{l}</button>
          ))}
        </div>

        {tab !== "settings" && (
          <div className="glass flex items-center gap-2 rounded-xl px-3">
            <Search className="h-4 w-4 text-primary" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Suchen …" className="w-full bg-transparent py-2.5 outline-none" />
          </div>
        )}
        {err && <p className="text-sm text-red-400">{err}</p>}

        {tab === "partners" && (
          <section className="space-y-2">
            {edit && (
              <form onSubmit={savePartner} className={`${card} grid gap-2 sm:grid-cols-2`}>
                <input className={field} value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} placeholder="Name" required />
                <select className={field} value={edit.type} onChange={(e) => setEdit({ ...edit, type: e.target.value })}>
                  {BUSINESS_TYPES.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}
                </select>
                <input className={field} value={edit.address ?? ""} onChange={(e) => setEdit({ ...edit, address: e.target.value })} placeholder="Adresse" />
                <input className={field} value={edit.offer} onChange={(e) => setEdit({ ...edit, offer: e.target.value })} placeholder="Angebot" />
                <select className={field} value={edit.owner_id ?? ""} onChange={(e) => setEdit({ ...edit, owner_id: e.target.value || null })}>
                  <option value="">Kein Inhaber</option>
                  {owners.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </select>
                <div className="flex gap-2">
                  <button className="flex-1 rounded-lg bg-primary py-2 font-semibold text-black">Speichern</button>
                  <button type="button" onClick={() => setEdit(null)} className={btn}>Abbrechen</button>
                </div>
              </form>
            )}
            <button className={btn} onClick={() => run(getSupabase().from("partners").insert({ name: "Neuer Partner", active: true }).then((r) => r))}>+ Partner manuell anlegen</button>
            {[...partners].sort((a, b) => Number(a.active) - Number(b.active))
              .filter((p) => `${p.name} ${p.address ?? ""}`.toLowerCase().includes(needle)).map((p) => (
              <div key={p.id} className={`${card} flex flex-wrap items-center justify-between gap-3 ${p.active ? "" : "border-amber-500/40"}`}>
                <div className="min-w-0">
                  <p className="truncate font-medium">{p.name} <span className="text-xs text-white/40">· {BUSINESS_TYPES.find((b) => b.value === p.type)?.label}</span></p>
                  <p className="truncate text-xs text-white/50">{p.address ?? "keine Adresse"} · {p.offer} · Inhaber: {p.owner_id ? names.get(p.owner_id) ?? "–" : "–"}{p.lat == null ? " · nicht auf Karte" : ""}</p>
                </div>
                <div className="flex gap-2">
                  <button className={btn} onClick={() => setEdit(p)}>Bearbeiten</button>
                  <button onClick={() => run(getSupabase().from("partners").update({ active: !p.active }).eq("id", p.id).then((r) => r))}
                    className={`${btn} ${p.active ? "text-emerald-400" : "text-amber-400"}`}>{p.active ? "Aktiv" : "Freigeben"}</button>
                </div>
              </div>
            ))}
          </section>
        )}

        {tab === "users" && (
          <section className="space-y-2">
            {profiles.filter((p) => (p.name ?? "").toLowerCase().includes(needle)).map((p) => {
              const pass = passOf.get(p.id);
              return (
                <div key={p.id} className={`${card} flex flex-wrap items-center justify-between gap-3`}>
                  <div>
                    <p className="font-medium">{p.name} {suspicious.has(p.id) && <span className="ml-1 rounded bg-red-500/20 px-1.5 text-xs text-red-400">Mehrfach-Scan 24h</span>}</p>
                    <p className="text-xs text-white/50">
                      {p.is_banned ? "Gesperrt" : "Aktiv"}{pass ? ` · Pass: ${pass.status}${pass.cooldown_until ? `, Cooldown bis ${new Date(pass.cooldown_until).toLocaleDateString("de-DE")}` : ""}` : ""}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <select value={p.role} disabled={p.id === me.id} className={`${field} py-1 text-xs`}
                      onChange={(e) => run(getSupabase().from("profiles").update({ role: e.target.value as Role }).eq("id", p.id).then((r) => r))}>
                      <option value="influencer">Creator</option><option value="partner">Partner</option><option value="admin">Admin</option>
                    </select>
                    <button className={btn} onClick={() => run(getSupabase().from("profiles").update({ trust_score: Math.max(0, p.trust_score - 10) }).eq("id", p.id).then((r) => r))}>−10</button>
                    <span className={`w-10 text-center font-mono text-lg ${p.trust_score < 30 ? "text-red-400" : "text-primary"}`}>{p.trust_score}</span>
                    <button className={btn} onClick={() => run(getSupabase().from("profiles").update({ trust_score: Math.min(100, p.trust_score + 10) }).eq("id", p.id).then((r) => r))}>+10</button>
                    {pass && (
                      <button title="Cooldown zurücksetzen & Pass aktivieren" className={btn}
                        onClick={() => run(getSupabase().from("creator_passes").update({ status: "active", cooldown_until: null }).eq("influencer_id", p.id).then((r) => r))}>
                        <RotateCcw className="h-3.5 w-3.5" />
                      </button>
                    )}
                    {p.id !== me.id && (
                      <button onClick={() => run(getSupabase().from("profiles").update({ is_banned: !p.is_banned }).eq("id", p.id).then((r) => r))}
                        className={`${btn} flex items-center gap-1 ${p.is_banned ? "text-emerald-400" : "text-red-400"}`}>
                        <Ban className="h-3.5 w-3.5" /> {p.is_banned ? "Entsperren" : "Bannen"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
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
                <div className="flex gap-2">
                  <button onClick={() => review(r.id, "verified")} disabled={!r.story_url || r.status === "verified"} className={`${btn} flex items-center gap-1 text-emerald-400 disabled:opacity-30`}>
                    <Check className="h-3.5 w-3.5" /> Story ok
                  </button>
                  <button onClick={() => review(r.id, "flagged")} disabled={r.status === "flagged"} className={`${btn} flex items-center gap-1 text-red-400 disabled:opacity-30`}>
                    <Flag className="h-3.5 w-3.5" /> Betrug
                  </button>
                </div>
              </div>
            ))}
          </section>
        )}

        {tab === "settings" && (
          <section className={`${card} space-y-4`}>
            {SETTINGS.map((s) => (
              <label key={s.key} className="block">
                <span className="text-sm font-medium">{s.label}</span>
                <span className="ml-2 text-xs text-white/40">{s.hint}</span>
                <input type="number" min={0} className={`${field} mt-1 block w-32`} value={settings[s.key] ?? ""}
                  onChange={(e) => setSettings({ ...settings, [s.key]: e.target.value })}
                  onBlur={(e) => e.target.value !== "" && run(getSupabase().from("app_settings").upsert({ key: s.key, value: String(Math.max(0, parseInt(e.target.value, 10) || 0)) }).then((r) => r))} />
              </label>
            ))}
            <p className="text-xs text-white/40">Änderungen gelten sofort für alle neuen Einlösungen.</p>
          </section>
        )}
      </div>
    </main>
  );
}
