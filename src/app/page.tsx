import Link from "next/link";
import { Camera, Coffee, QrCode, ShieldCheck } from "lucide-react";
import { Brand } from "@/components/Shell";
import PartnerMap from "@/components/PartnerMap";

const STEPS = [
  { icon: QrCode, title: "Pass sichern", text: "Registriere dich und erhalte deine digitale Black Card mit QR-Code." },
  { icon: Coffee, title: "Drink einlösen", text: "Zeige den Pass bei einem der Partner in Nürnberg – der Barista scannt." },
  { icon: Camera, title: "Story posten", text: "Teile deine Story, reiche den Link ein und schalte den Pass wieder frei." },
];

export default function Home() {
  return (
    <main className="mx-auto max-w-5xl px-4 pb-20">
      <nav className="flex items-center justify-between py-5">
        <Brand />
        <Link href="/login" className="glass rounded-full px-4 py-2 text-sm">Login</Link>
      </nav>

      <section className="py-14 text-center sm:py-24">
        <p className="mb-4 text-xs uppercase tracking-[0.3em] text-primary">Nürnberg Creator &amp; Partner Network</p>
        <h1 className="text-4xl font-bold leading-tight sm:text-6xl">
          Dein <span className="gold-text">Freigetränk</span> für Reichweite in Nürnberg
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-white/65">
          Über 100 Cafés, Bars und Lounges. Du postest, sie schenken ein. Exklusiv, fair und mit einem Scan erledigt.
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link href="/login?mode=register" className="w-full rounded-full bg-primary px-8 py-3.5 font-semibold text-black shadow-[0_0_30px_rgba(212,175,55,0.35)] active:scale-95 sm:w-auto">
            Black Card sichern
          </Link>
          <Link href="/login?mode=partner" className="glass w-full rounded-full px-8 py-3.5 font-medium sm:w-auto">
            Als Partner mitmachen
          </Link>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {STEPS.map(({ icon: Icon, title, text }, i) => (
          <div key={title} className="glass rounded-2xl p-5">
            <Icon className="h-6 w-6 text-primary" />
            <p className="mt-3 font-semibold">{i + 1}. {title}</p>
            <p className="mt-1 text-sm text-white/60">{text}</p>
          </div>
        ))}
      </section>

      <section className="mt-16">
        <h2 className="mb-4 text-2xl font-semibold">Partner in deiner <span className="gold-text">Nähe</span></h2>
        <PartnerMap />
      </section>

      <section className="glass mt-16 flex flex-col items-center gap-3 rounded-3xl p-8 text-center">
        <ShieldCheck className="h-8 w-8 text-primary" />
        <h2 className="text-xl font-semibold">Fair für beide Seiten</h2>
        <p className="max-w-lg text-sm text-white/60">
          Trust-Score, Cooldown und Betrugsprävention schützen unsere Partner – und deinen Status als Creator.
        </p>
        <Link href="/login?mode=register" className="mt-2 rounded-full bg-primary px-6 py-3 font-semibold text-black active:scale-95">Jetzt starten</Link>
      </section>
    </main>
  );
}
