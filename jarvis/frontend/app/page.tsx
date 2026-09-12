"use client";

import { useEffect, useRef, useState } from "react";
import ChatMessage, { Message } from "@/components/ChatMessage";
import ConnectionModal from "@/components/ConnectionModal";
import VoiceOrb, { OrbState } from "@/components/VoiceOrb";
import {
  JarvisApiError,
  getStoredConnection,
  hasConnection,
  sendChatMessage,
  speakText,
  transcribeAudio,
} from "@/lib/api";

function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}

export default function JarvisPage() {
  const [connected, setConnected] = useState(false);
  const [showConnectionModal, setShowConnectionModal] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      text: "Guten Tag, Master. Ich bin bereit. Womit kann ich behilflich sein?",
    },
  ]);
  const [input, setInput] = useState("");
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    setConnected(hasConnection());
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function handleSend(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (!connected) {
      setShowConnectionModal(true);
      return;
    }

    setError(null);
    setInput("");
    setMessages((prev) => [...prev, { id: uid(), role: "user", text: trimmed }]);
    setOrbState("thinking");

    try {
      const response = await sendChatMessage(trimmed, sessionId);
      setSessionId(response.session_id);
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "assistant", text: response.reply, modelUsed: response.model_used },
      ]);

      if (voiceEnabled) {
        await playReply(response.reply);
      } else {
        setOrbState("idle");
      }
    } catch (err) {
      setOrbState("idle");
      setError(err instanceof JarvisApiError ? err.message : "Unerwarteter Fehler.");
    }
  }

  async function playReply(text: string) {
    try {
      setOrbState("speaking");
      const blob = await speakText(text);
      const url = URL.createObjectURL(blob);
      if (audioRef.current) {
        audioRef.current.src = url;
        await audioRef.current.play();
        audioRef.current.onended = () => setOrbState("idle");
      } else {
        setOrbState("idle");
      }
    } catch {
      // TTS ist optional - lautlos zurück in den Ruhezustand, Text steht ja schon im Chat.
      setOrbState("idle");
    }
  }

  async function handleMicToggle() {
    if (!connected) {
      setShowConnectionModal(true);
      return;
    }

    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      audioChunksRef.current = [];
      recorder.ondataavailable = (e) => audioChunksRef.current.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        setOrbState("thinking");
        try {
          const text = await transcribeAudio(blob);
          if (text) await handleSend(text);
          else setOrbState("idle");
        } catch (err) {
          setOrbState("idle");
          setError(err instanceof JarvisApiError ? err.message : "Transkription fehlgeschlagen.");
        }
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
      setOrbState("listening");
    } catch {
      setError("Mikrofon-Zugriff wurde verweigert oder ist nicht verfügbar.");
    }
  }

  const { baseUrl } = getStoredConnection();

  return (
    <main className="mx-auto flex h-screen max-w-3xl flex-col px-4 py-6">
      <header className="flex items-center justify-between pb-4">
        <div className="flex items-center gap-3">
          <VoiceOrb state={orbState} />
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-white">Jarvis</h1>
            <p className="text-xs text-white/40">
              {connected ? "Verbunden" : "Nicht verbunden"} · {orbState}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setVoiceEnabled((v) => !v)}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
              voiceEnabled
                ? "border-jarvis-accent/50 bg-jarvis-accent/10 text-jarvis-accent"
                : "border-jarvis-border text-white/40"
            }`}
            title="Sprachausgabe an/aus"
          >
            🔊 Stimme
          </button>
          {connected && baseUrl && (
            <a
              href={`${baseUrl}/admin`}
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-jarvis-border px-3 py-1.5 text-xs font-medium text-white/60 hover:text-white"
            >
              ⚙ Connectors
            </a>
          )}
          <button
            onClick={() => setShowConnectionModal(true)}
            className="rounded-full border border-jarvis-border px-3 py-1.5 text-xs font-medium text-white/60 hover:text-white"
          >
            {connected ? "Server wechseln" : "Verbinden"}
          </button>
        </div>
      </header>

      <div
        ref={scrollRef}
        className="scroll-fade-top flex-1 space-y-3 overflow-y-auto rounded-2xl border border-jarvis-border bg-jarvis-panel/40 p-4"
      >
        {messages.map((m) => (
          <ChatMessage key={m.id} message={m} />
        ))}
      </div>

      {error && <p className="mt-2 text-xs text-jarvis-err">{error}</p>}

      <div className="mt-4 flex items-center gap-2">
        <button
          onClick={handleMicToggle}
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full border transition-colors ${
            isRecording
              ? "border-jarvis-err bg-jarvis-err/20 text-jarvis-err"
              : "border-jarvis-border bg-jarvis-panel2 text-white/70 hover:text-white"
          }`}
          title="Spracheingabe"
        >
          {isRecording ? "■" : "🎤"}
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend(input)}
          placeholder="Nachricht an Jarvis..."
          className="flex-1 rounded-full border border-jarvis-border bg-jarvis-panel2 px-4 py-3 text-sm text-white outline-none focus:border-jarvis-accent"
        />
        <button
          onClick={() => handleSend(input)}
          disabled={!input.trim()}
          className="rounded-full bg-gradient-to-r from-jarvis-accent to-jarvis-accent2 px-5 py-3 text-sm font-semibold text-white disabled:opacity-40"
        >
          Senden
        </button>
      </div>

      <audio ref={audioRef} hidden />

      {(showConnectionModal || !connected) && (
        <ConnectionModal
          initialUrl={getStoredConnection().baseUrl}
          initialToken={getStoredConnection().token}
          onConnected={() => {
            setConnected(true);
            setShowConnectionModal(false);
          }}
          onClose={connected ? () => setShowConnectionModal(false) : undefined}
        />
      )}
    </main>
  );
}
