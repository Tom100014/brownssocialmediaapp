"use client";

import { useEffect, useState } from "react";
import { MapPin } from "lucide-react";
import { BUSINESS_TYPES, getSupabase, type Partner } from "@/lib/supabase";

// Nürnberg bounding box for projecting lat/lng onto the stylized map
const BOX = { latMin: 49.38, latMax: 49.52, lngMin: 10.98, lngMax: 11.22 };

const DEMO: Partner[] = [
  { id: "d1", name: "Altstadt Espresso Bar", type: "cafe", lat: 49.4521, lng: 11.0767, offer: "Gratis Flat White", address: "Altstadt", owner_id: null, active: true },
  { id: "d2", name: "Kaiserburg Rooftop", type: "bar", lat: 49.4579, lng: 11.0757, offer: "Gratis Signature Drink", address: "Burg", owner_id: null, active: true },
  { id: "d3", name: "Gostenhof Roasters", type: "cafe", lat: 49.4515, lng: 11.0476, offer: "Gratis Cold Brew", address: "Gostenhof", owner_id: null, active: true },
];

const typeLabel = (t: string) => BUSINESS_TYPES.find((b) => b.value === t)?.label ?? t;

export default function PartnerMap() {
  const [partners, setPartners] = useState<Partner[]>([]);
  const [demo, setDemo] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    getSupabase().rpc("list_public_partners").then(({ data, error }) => {
      const list = ((data ?? []) as Partner[]).filter((p) => p.lat != null && p.lng != null);
      if (error || list.length === 0) {
        setDemo(true);
        setPartners(DEMO);
      } else setPartners(list);
    });
  }, []);

  const p = partners[active];
  const pos = (q: Partner) => ({
    left: `${Math.min(95, Math.max(5, (((q.lng ?? 0) - BOX.lngMin) / (BOX.lngMax - BOX.lngMin)) * 100))}%`,
    top: `${Math.min(95, Math.max(8, (1 - ((q.lat ?? 0) - BOX.latMin) / (BOX.latMax - BOX.latMin)) * 100))}%`,
  });

  return (
    <div className="glass overflow-hidden rounded-3xl">
      <div className="relative aspect-[4/3] w-full bg-[radial-gradient(circle_at_50%_40%,rgba(212,175,55,0.10),transparent_65%)]">
        <svg className="absolute inset-0 h-full w-full opacity-40" viewBox="0 0 100 75" preserveAspectRatio="none" aria-hidden>
          <defs>
            <pattern id="g" width="6" height="6" patternUnits="userSpaceOnUse">
              <path d="M6 0H0V6" fill="none" stroke="#D4AF37" strokeOpacity="0.15" strokeWidth="0.2" />
            </pattern>
          </defs>
          <rect width="100" height="75" fill="url(#g)" />
          <path d="M0 48 C 25 40, 40 58, 60 46 S 90 38, 100 44" fill="none" stroke="#D4AF37" strokeOpacity="0.35" strokeWidth="0.8" />
          <rect x="30" y="22" width="40" height="34" rx="14" fill="none" stroke="#D4AF37" strokeOpacity="0.4" strokeDasharray="1.5 1.5" strokeWidth="0.4" />
        </svg>
        {partners.map((q, i) => (
          <button key={q.id} onClick={() => setActive(i)} aria-label={q.name} style={pos(q)}
            className="absolute -translate-x-1/2 -translate-y-full transition-transform hover:scale-125 active:scale-95">
            <MapPin className={`h-8 w-8 drop-shadow ${i === active ? "fill-primary text-black" : "fill-secondary text-primary"}`} />
          </button>
        ))}
      </div>
      {p && (
        <div className="flex items-center justify-between gap-4 border-t border-primary/15 p-4">
          <div className="min-w-0">
            <p className="truncate font-semibold">{p.name}</p>
            <p className="truncate text-sm text-white/60">{typeLabel(p.type)} · {p.address ?? "Nürnberg"}</p>
          </div>
          <span className="shrink-0 rounded-full bg-primary/15 px-3 py-1 text-sm text-primary">{p.offer}</span>
        </div>
      )}
      {demo && <p className="border-t border-primary/10 px-4 py-2 text-center text-xs text-white/40">Beispiel-Partner – echte Partner erscheinen nach der Freigabe</p>}
    </div>
  );
}
