"use client";

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  modelUsed?: string;
}

export default function ChatMessage({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex animate-rise ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-lg ${
          isUser
            ? "bg-gradient-to-br from-jarvis-accent to-jarvis-accent2 text-white"
            : "border border-jarvis-border bg-jarvis-panel text-white/90"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.text}</p>
        {message.modelUsed && (
          <p className="mt-1.5 text-[10px] uppercase tracking-wide text-white/40">
            {message.modelUsed === "claude-sonnet" ? "Claude Sonnet" : "Gemini Flash"}
          </p>
        )}
      </div>
    </div>
  );
}
