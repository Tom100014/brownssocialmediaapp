# Jarvis

Ein autarker, modularer KI-Betriebsassistent: FastAPI-Backend (Hybrid-Routing
zwischen Claude Sonnet und Gemini Flash, 14 deterministische Tools, Voice
in/out, verschlüsselter Connector-Store) + Next.js-Frontend.

```
jarvis/
├── config.py            Zentrale, validierte Konfiguration
├── storage.py            SQLite + Verschlüsselung (Fernet)
├── connectors_manager.py Connector-CRUD (API-Keys etc.)
├── brain_router.py       Hybrid-Routing Flash/Sonnet, Persona, Gedächtnis
├── tools_manager.py       14 Tools (Kalender, Tasks, Notizen, Leads, ...)
├── audio_pipeline.py      Deepgram STT / ElevenLabs TTS
├── server_api.py          FastAPI-Endpunkte + /admin-Weboberfläche
├── local_client.py        Polling-Daemon für den Laptop
└── frontend/              Next.js-Chat-Oberfläche (siehe frontend/README.md)
```

## Backend deployen (Railway - empfohlen)

Railway hostet den FastAPI-Server dauerhaft inkl. automatischem HTTPS - im
Gegensatz zu Vercel, das nur kurzlebige Funktionen ausführt und daher für
diesen Server (persistenter Zustand, SQLite, Live-Verbindungen) nicht
geeignet ist.

1. Auf [railway.app](https://railway.app) einloggen (GitHub-Login).
2. **New Project → Deploy from GitHub repo** → `tom100014/brownssocialmediaapp`
   auswählen, Branch `claude/jarvis-ai-assistant-build-8apjsa`.
3. Im Service unter **Settings → Root Directory**: `jarvis` eintragen.
   Railway erkennt dann automatisch `railway.json` (Start-Command,
   Health-Check) und `requirements.txt`.
4. Unter **Variables** setzen (Pflicht):
   - `API_AUTH_TOKEN` - frei wählbares, langes Passwort für dein Backend
   - `JARVIS_MASTER_KEY` - erzeugen mit:
     ```bash
     python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```
     (fest setzen, sonst würde bei jedem Neustart ohne Volume ein neuer
     Schlüssel erzeugt und bereits gespeicherte Connector-Keys wären
     unlesbar)
   - `CORS_ALLOWED_ORIGINS` - die URL deines Vercel-Frontends, z. B.
     `https://jarvis-frontend.vercel.app` (mehrere Origins kommagetrennt)
5. Unter **Settings → Volumes**: Volume hinzufügen, **Mount Path**: `/app/data`.
   Das sichert die SQLite-Datenbank (Connectors, Kalender, Tasks, Gedächtnis)
   dauerhaft gegen Redeploys - ohne Volume geht der Inhalt bei jedem Deploy
   verloren.
6. Deploy abwarten, dann die von Railway vergebene Domain öffnen:
   `https://<dein-projekt>.up.railway.app/health` sollte `{"status":"ok"}`
   zeigen.
7. `https://<dein-projekt>.up.railway.app/admin` öffnen, mit deinem
   `API_AUTH_TOKEN` anmelden und dort Anthropic/Gemini/Deepgram/ElevenLabs/
   Wetter-Connectors eintragen (siehe unten).

Alle übrigen Variablen aus `.env.example` sind optional (Fallbacks bzw.
haben sinnvolle Defaults) und lassen sich später auch direkt über den
Connector-Store (`/admin` bzw. `PUT /connectors`, `PUT /settings`) ändern,
ohne den Dienst neu zu deployen.

### Alternativen zu Railway

**Render** ("Web Service", Root Directory `jarvis`, Start-Command wie oben,
persistenter Disk unter `/app/data`) oder **Fly.io** funktionieren nach dem
gleichen Prinzip. Ein eigener Linux-Server mit systemd + Caddy (Reverse-Proxy
für HTTPS) geht ebenfalls, erfordert aber mehr manuelle Pflege.

## Frontend deployen (Vercel)

Siehe [`frontend/README.md`](frontend/README.md). Kurzfassung: Root
Directory `jarvis/frontend`, optional `NEXT_PUBLIC_JARVIS_API_URL` als
Environment Variable setzen, deployen. Danach im Frontend einmalig die
Railway-URL + `API_AUTH_TOKEN` eintragen.

## Lokale Entwicklung

```bash
cd jarvis
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ausfüllen
uvicorn server_api:app --reload --port 8420
```
