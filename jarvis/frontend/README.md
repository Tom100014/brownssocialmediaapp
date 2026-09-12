# Jarvis Frontend

Next.js-Chat-Oberfläche für den Jarvis-Assistenten. Läuft komplett im Browser
und spricht per HTTPS mit deinem Jarvis-Server (`server_api.py`) - das
Frontend selbst speichert keine Secrets, sondern nur Server-URL und
API-Token im `localStorage` des Browsers.

## Features

- Chat mit Claude Sonnet / Gemini Flash (automatisches Hybrid-Routing im Backend)
- Spracheingabe (Mikrofon-Aufnahme -> `/voice/transcribe`)
- Sprachausgabe (Antwort -> `/voice/speak`, automatische Wiedergabe, abschaltbar)
- Direkter Link zur Connector-Verwaltung (`/admin` auf dem Server)

## Lokal starten

```bash
npm install
npm run dev
```

Dann `http://localhost:3000` öffnen und beim ersten Start Server-URL +
`API_AUTH_TOKEN` deines Jarvis-Servers eintragen.

## Deployment auf Vercel

1. Repository (bzw. diesen `jarvis/frontend`-Ordner als "Root Directory") in
   Vercel importieren.
2. Optional als Environment Variable setzen: `NEXT_PUBLIC_JARVIS_API_URL`
   (Standard-Server-URL, falls der Nutzer noch keine eigene hinterlegt hat).
3. Deployen - fertig. Das Backend (FastAPI) läuft weiterhin auf deinem
   eigenen Server; Vercel hostet ausschließlich dieses Next.js-Frontend.

Wichtig: `server_api.py` muss von außen per HTTPS erreichbar sein (Reverse
Proxy mit TLS, z. B. nginx/Caddy vor Uvicorn), sonst blockiert der Browser
gemischte HTTP/HTTPS-Inhalte bzw. CORS.
