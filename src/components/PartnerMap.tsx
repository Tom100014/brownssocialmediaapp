"use client";

import { useState } from "react";
import { MapPin } from "lucide-react";

const PARTNERS = [
  { name: "Altstadt Espresso Bar", kind: "Café", x: 48, y: 42, perk: "Gratis Flat White" },
  { name: "Kaiserburg Rooftop", kind: "Bar", x: 40, y: 22, perk: "Gratis Signature Drink" },
  { name: "Gostenhof Roasters", kind: "Café", x: 24, y: 55, perk: "Gratis Cold Brew" },
  { name: "Südstadt Social Club", kind: "Lounge", x: 52, y: 72, perk: "Gratis Softdrink" },
  { name: "Hauptbahnhof Juice Lab", kind: "Juice", x: 66, y: 50, perk: "Gratis Smoothie" },
  { name: "Johannis Tea House", kind: "Tea", x: 30, y: 30, perk: "Gratis Matcha" },
];

export default function PartnerMap() {
  const [active, setActive] = useState(0);
  const p = PARTNERS[active];
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
        {PARTNERS.map((q, i) => (
          <button
            key={q.name}
            onClick={() => setActive(i)}
            aria-label={q.name}
            style={{ left: `${q.x}%`, top: `${q.y}%` }}
            className="absolute -translate-x-1/2 -translate-y-full transition-transform hover:scale-125 active:scale-95"
          >
            <MapPin className={`h-8 w-8 drop-shadow ${i === active ? "fill-primary text-black" : "fill-secondary text-primary"}`} />
          </button>
        ))}
      </div>
      <div className="flex items-center justify-between gap-4 border-t border-primary/15 p-4">
        <div>
          <p className="font-semibold">{p.name}</p>
          <p className="text-sm text-white/60">{p.kind} · Nürnberg</p>
        </div>
        <span className="rounded-full bg-primary/15 px-3 py-1 text-sm text-primary">{p.perk}</span>
      </div>
    </div>
  );
}
