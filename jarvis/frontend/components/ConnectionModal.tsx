"use client";

import { useState } from "react";
import { checkHealth, saveConnection } from "@/lib/api";

export default function ConnectionModal({
  initialUrl,
  initialToken,
  onConnected,
  onClose,
}: {
  initialUrl: string;
  initialToken: string;
  onConnected: () => void;
  onClose?: () => void;
}) {
  const [url, setUrl] = useState(initialUrl);
  const [token, setToken] = useState(initialToken);
  const [status, setStatus] = useState<"idle" | "checking" | "ok" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");

  async function handleConnect() {
    setStatus("checking");
    const ok = await checkHealth(url);
    if (!ok) {
      setStatus("error");
      setErrorMessage("Server nicht erreichbar. URL prüfen (z. B. https://dein-server:8420).");
      return;
    }
    saveConnection(url, token);
    setStatus("ok");
    onConnected();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-md rounded-2xl border border-jarvis-border bg-jarvis-panel p-6 shadow-2xl animate-rise">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">Mit Jarvis verbinden</h2>
            <p className="mt-1 text-sm text-white/50">
              Gib die Adresse deines Jarvis-Servers und dein API-Token ein.
            </p>
          </div>
          {onClose && (
            <button onClick={onClose} className="text-white/40 hover:text-white" aria-label="Schließen">
              ✕
            </button>
          )}
        </div>

        <div className="mt-5 space-y-3">
          <div>
            <label className="mb-1 block text-xs text-white/50">Server-URL</label>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://jarvis.deinserver.de"
              className="w-full rounded-lg border border-jarvis-border bg-jarvis-panel2 px-3 py-2 text-sm text-white outline-none focus:border-jarvis-accent"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-white/50">API-Token</label>
            <input
              value={token}
              onChange={(e) => setToken(e.target.value)}
              type="password"
              placeholder="API_AUTH_TOKEN"
              className="w-full rounded-lg border border-jarvis-border bg-jarvis-panel2 px-3 py-2 text-sm text-white outline-none focus:border-jarvis-accent"
            />
          </div>
        </div>

        {status === "error" && <p className="mt-3 text-xs text-jarvis-err">{errorMessage}</p>}

        <button
          onClick={handleConnect}
          disabled={!url || !token || status === "checking"}
          className="mt-5 w-full rounded-lg bg-gradient-to-r from-jarvis-accent to-jarvis-accent2 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {status === "checking" ? "Verbinde..." : "Verbinden"}
        </button>
      </div>
    </div>
  );
}
