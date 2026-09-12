"use client";

export type OrbState = "idle" | "listening" | "thinking" | "speaking";

const STATE_STYLES: Record<OrbState, string> = {
  idle: "from-jarvis-accent/40 to-jarvis-accent2/30",
  listening: "from-jarvis-ok/60 to-jarvis-accent/50 animate-pulseGlow",
  thinking: "from-jarvis-accent2/70 to-jarvis-accent/60 animate-pulseGlow",
  speaking: "from-jarvis-accent/80 to-jarvis-accent2/70 animate-pulseGlow",
};

export default function VoiceOrb({ state }: { state: OrbState }) {
  return (
    <div className="relative flex h-16 w-16 items-center justify-center">
      <div
        className={`absolute h-16 w-16 rounded-full bg-gradient-to-br blur-xl transition-all duration-500 ${STATE_STYLES[state]}`}
      />
      <div className="relative h-10 w-10 rounded-full bg-gradient-to-br from-jarvis-accent to-jarvis-accent2 shadow-[0_0_30px_rgba(91,140,255,0.5)]" />
    </div>
  );
}
