"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { Check, ScanLine, X } from "lucide-react";
import { getSupabase, PASS_PREFIX } from "@/lib/supabase";
import { signOut, useProfile } from "@/lib/useProfile";
import { Header, Loading } from "@/components/Shell";

interface Partner { id: string; name: string }
interface Result { ok: boolean; reason?: string; name?: string }

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function Scanner() {
  const profile = useProfile("partner");
  const [partners, setPartners] = useState<Partner[]>([]);
  const [partnerId, setPartnerId] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const scanner = useRef<Html5Qrcode | null>(null);
  const handling = useRef(false);

  useEffect(() => {
    if (!profile) return;
    getSupabase().from("partners").select("id,name").eq("active", true).then(({ data }) => {
      const list = (data ?? []) as Partner[];
      setPartners(list);
      if (list[0]) setPartnerId(list[0].id);
    });
  }, [profile]);

  const handleScan = useCallback(async (text: string) => {
    if (handling.current) return;
    handling.current = true;
    const token = text.startsWith(PASS_PREFIX) ? text.slice(PASS_PREFIX.length) : "";
    let res: Result;
    if (!UUID.test(token) || !partnerId) {
      res = { ok: false, reason: "Ungültiger QR-Code" };
    } else {
      const { data, error } = await getSupabase().rpc("redeem_pass", { p_token: token, p_partner_id: partnerId });
      res = error ? { ok: false, reason: error.message } : (data as Result);
    }
    navigator.vibrate?.(res.ok ? 120 : [80, 60, 80]);
    setResult(res);
    setTimeout(() => {
      setResult(null);
      handling.current = false;
    }, res.ok ? 2500 : 3500);
  }, [partnerId]);

  useEffect(() => {
    if (!profile || !partnerId) return;
    const s = new Html5Qrcode("qr-reader");
    scanner.current = s;
    s.start({ facingMode: "environment" }, { fps: 10, qrbox: { width: 240, height: 240 } }, handleScan, () => {})
      .catch(() => setError("Kamera nicht verfügbar. Bitte Zugriff erlauben."));
    return () => {
      if (s.isScanning) s.stop().then(() => s.clear()).catch(() => {});
    };
  }, [profile, partnerId, handleScan]);

  if (!profile) return <Loading />;

  return (
    <main className="pb-10">
      <Header title="Barista Scanner" onSignOut={signOut} />
      <div className="mx-auto max-w-md space-y-4 px-4">
        {partners.length === 0 ? (
          <p className="glass rounded-2xl p-4 text-center text-sm text-white/60">Deinem Account ist kein aktiver Partner zugewiesen.</p>
        ) : (
          <select
            value={partnerId} onChange={(e) => setPartnerId(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-secondary px-4 py-3"
          >
            {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        )}
        <div className="glass overflow-hidden rounded-3xl p-2">
          <div id="qr-reader" className="overflow-hidden rounded-2xl" />
          {error && <p className="p-4 text-center text-sm text-red-400">{error}</p>}
        </div>
        <p className="flex items-center justify-center gap-2 text-sm text-white/50"><ScanLine className="h-4 w-4 text-primary" /> QR-Code im Rahmen halten</p>
      </div>

      {result && (
        <div className={`flash-in fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 p-8 text-center ${result.ok ? "bg-emerald-600" : "bg-red-600"}`}>
          {result.ok ? <Check className="h-32 w-32" strokeWidth={3} /> : <X className="h-32 w-32" strokeWidth={3} />}
          <p className="text-4xl font-bold">{result.ok ? "FREIGEGEBEN" : "ABGELEHNT"}</p>
          {result.name && <p className="text-xl opacity-90">{result.name}</p>}
          {!result.ok && <p className="text-lg opacity-90">{result.reason}</p>}
          {result.ok && <p className="text-lg opacity-90">Freigetränk ausgeben ✓</p>}
        </div>
      )}
    </main>
  );
}
