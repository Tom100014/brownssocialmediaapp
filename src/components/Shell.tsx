import Link from "next/link";
import { Gem, LogOut } from "lucide-react";

export function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2 font-semibold tracking-wide">
      <Gem className="h-5 w-5 text-primary" />
      <span className="gold-text">BLACK CARD</span>
    </Link>
  );
}

export function Header({ title, onSignOut }: { title: string; onSignOut: () => void }) {
  return (
    <header className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
      <div>
        <Brand />
        <p className="mt-1 text-xs uppercase tracking-widest text-white/50">{title}</p>
      </div>
      <button onClick={onSignOut} className="glass flex items-center gap-2 rounded-full px-4 py-2 text-sm text-white/80 active:scale-95">
        <LogOut className="h-4 w-4" /> Logout
      </button>
    </header>
  );
}

export function Loading() {
  return <div className="grid min-h-dvh place-items-center text-primary/80">Lade …</div>;
}
