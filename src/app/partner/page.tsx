"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Clock, MapPin, Plus, ScanLine } from "lucide-react";
import { BUSINESS_TYPES, geocode, getSupabase, type Partner } from "@/lib/supabase";
import { signOut, useProfile } from "@/lib/useProfile";
import { Header, Loading } from "@/components/Shell";

interface Scan { id: string; creator_name: string; status: string; redeemed_at: string }

const field = "w-full rounded-lg border border-white/10 bg-secondary px-3 py-2 outline-none focus:border-primary";

function Location({ p, onSaved }: { p: Partner; onSaved: () => void }) {
  const [f, setF] = useState({ name: p.name, type: p.type, address: p.address ?? "", offer: p.offer });
  const [scans, setScans] = useState<Scan[]>([]);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    getSupabase().rpc("partner_scans", { p_partner_id: p.id, p_limit: 10 }).then(({ data }) => setScans((data ?? []) as Scan[]));
  }, [p.id]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setMsg("Speichere …");
    const geo = f.address !== (p.address ?? "") || p.lat == null ? await geocode(f.address) : { lat: p.lat, lng: p.lng };
    const { error } = await getSupabase().from("partners").update({ ...f, lat: geo?.lat ?? null, lng: geo?.lng ?? null }).eq("id", p.id);
    setMsg(error ? error.message : geo ? "Gespeichert ✓" : "Gespeichert – Adresse nicht auf der Karte gefunden");
    onSaved();
  }

  return (
    <section className="glass space-y-3 rounded-3xl p-5">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2 font-semibold"><MapPin className="h-4 w-4 text-primary" /> {p.name}</p>
        <span className={`rounded-full px-3 py-1 text-xs ${p.active ? "bg-emerald-500/15 text-emerald-400" : "bg-amber-500/15 text-amber-400"}`}>
          {p.active ? "Freigeschaltet" : "Wartet auf Freigabe"}
        </span>
      </div>
      <form onSubmit={save} className="space-y-2">
        <input className={field} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Name" required />
        <select className={field} value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>
          {BUSINESS_TYPES.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}
        </select>
        <input className={field} value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} placeholder="Adresse" required />
        <input className={field} value={f.offer} onChange={(e) => setF({ ...f, offer: e.target.value })} placeholder="Angebot" required />
        <button className="w-full rounded-lg bg-primary py-2.5 font-semibold text-black active:scale-95">Speichern</button>
        {msg && <p className="text-center text-xs text-white/60">{msg}</p>}
      </form>
      <div>
        <p className="mb-2 flex items-center gap-2 text-sm text-white/60"><Clock className="h-4 w-4" /> Letzte Einlösungen</p>
        {scans.length === 0 ? <p className="text-sm text-white/40">Noch keine.</p> : (
          <ul className="space-y-1 text-sm">
            {scans.map((s) => (
              <li key={s.id} className="flex justify-between"><span>{s.creator_name}</span>
                <span className="text-white/50">{new Date(s.redeemed_at).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" })}</span></li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export default function PartnerHome() {
  const profile = useProfile("partner");
  const [list, setList] = useState<Partner[]>([]);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    const q = getSupabase().from("partners").select("*").order("created_at");
    const { data } = await (profile?.role === "admin" ? q : q.eq("owner_id", profile?.id ?? ""));
    setList((data ?? []) as Partner[]);
  }, [profile]);

  useEffect(() => {
    if (profile) load();
  }, [profile, load]);

  async function addLocation() {
    if (!profile) return;
    const { error } = await getSupabase().from("partners").insert({ name: "Neuer Standort", owner_id: profile.id, active: false });
    setErr(error?.message ?? "");
    load();
  }

  if (!profile) return <Loading />;

  return (
    <main className="pb-16">
      <Header title={`Partner · ${profile.name ?? ""}`} onSignOut={signOut} />
      <div className="mx-auto max-w-md space-y-5 px-4">
        <Link href="/partner/scanner" className="flex items-center justify-center gap-3 rounded-3xl bg-primary py-5 text-lg font-bold text-black shadow-[0_0_40px_rgba(212,175,55,0.3)] active:scale-95">
          <ScanLine className="h-6 w-6" /> Scanner öffnen
        </Link>
        {list.map((p) => <Location key={p.id} p={p} onSaved={load} />)}
        {list.length === 0 && <p className="glass rounded-2xl p-4 text-center text-sm text-white/60">Noch kein Betrieb hinterlegt.</p>}
        <button onClick={addLocation} className="glass flex w-full items-center justify-center gap-2 rounded-2xl py-3 text-sm"><Plus className="h-4 w-4" /> Weiteren Standort hinzufügen</button>
        {err && <p className="text-center text-sm text-red-400">{err}</p>}
      </div>
    </main>
  );
}
