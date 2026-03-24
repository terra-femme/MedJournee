# MedJournee — Render Deployment

**Last updated:** 2026-03-24

---

## Architecture on Render

MedJournee runs as a single Render web service. The FastAPI backend serves both the API and the PWA frontend (static HTML files). There is no separate static hosting — everything goes through one service.

```
Render Web Service (MedJournee_Backend)
  └── FastAPI (uvicorn)
        ├── /             → static/mobile.html (PWA entry)
        ├── /static/**    → static files (HTML, CSS, JS, icons)
        ├── /sw.js        → static/sw.js (service worker, root scope)
        └── /api/**       → backend routes (journal, appointments, etc.)
```

HTTPS is provided automatically and for free by Render. This is required — the service worker will not register without HTTPS (localhost gets a free pass for local dev).

---

## render.yaml

```yaml
services:
  - type: web
    name: MedJournee_Backend
    runtime: python
    pythonVersion: "3.11.9"
    buildCommand: pip install -r requirements-render.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Important:** `render.yaml` and `requirements-render.txt` are listed in `.gitignore` and are NOT committed to the GitHub repo. This means:

- After reconnecting the repo to GitHub post-SSD rebuild, Render will not auto-detect the config
- You must manually configure the service in the Render dashboard (see steps below)

`requirements-render.txt` is the trimmed production dependency list — it excludes heavy dev/ML packages like PyTorch and pyannote. Do not use `requirements.txt` on Render; it is also UTF-16 encoded which breaks `pip install` on Linux.

---

## Environment Variables Required on Render

Set these in the Render dashboard under your service → Environment:

| Variable | Required | Notes |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Whisper + GPT-4 |
| `ASSEMBLYAI_API_KEY` | Yes | Diarization |
| `GLADIA_API_KEY` | Yes | Real-time WebSocket transcription |
| `SUPABASE_URL` | Yes | Your Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase anon key |
| `SUPABASE_SERVICE_KEY` | Recommended | Service role key (falls back to anon if empty) |
| `VOICE_ENCRYPTION_KEY` | Yes | Fernet key for voice embedding encryption |
| `SUPABASE_JWT_SECRET` | Yes | Required for JWT auth middleware |
| `METRICS_API_KEY` | Optional | Protects `/metrics` endpoint |
| `GOOGLE_TRANSLATE_API_KEY` | Optional | Falls back to deep-translator if not set |

**Never put these values in the codebase.** They live only in the Render dashboard and your local `.env` file.

---

## Deploying After SSD Rebuild (Step-by-Step)

### Step 1 — Push code to GitHub

```bash
cd /c/Users/aznkr/Documents/Portfolio/MedJournee
git init
git remote add origin https://github.com/terra-femme/MedJournee.git
git fetch origin
# Verify .env is NOT staged before committing
git status
git add .
git commit -m "Reconnect after SSD rebuild"
git push origin main
```

### Step 2 — Connect repo to Render

1. Go to [render.com](https://render.com) → your existing `MedJournee_Backend` service
2. Settings → Build & Deploy → connect to `terra-femme/MedJournee`

Or if creating the service fresh:
1. Render → New → **Web Service**
2. Connect `terra-femme/MedJournee` repo
3. Fill in:

| Field | Value |
|---|---|
| Name | MedJournee_Backend |
| Runtime | Python 3 |
| Python Version | 3.11.9 |
| Build Command | `pip install -r requirements-render.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | Free |

### Step 3 — Set environment variables

In the Render dashboard → your service → Environment → add all variables from the table above.

### Step 4 — Deploy

Click **Manual Deploy → Deploy latest commit**. Build takes 2–5 minutes.

Render will give you a URL like:
```
https://medjournee-backend.onrender.com
```

### Step 5 — Verify config.js has the correct Render URL

`static/js/config.js` is already set to:

```js
RENDER: 'https://medjournee-backend.onrender.com'
```

No action needed — this is already correct.

---

## Normal Deploy (After Initial Setup)

Render auto-deploys on every push to `main`. Just push:

```bash
git add .
git commit -m "your message"
git push
```

New version live in 2–5 minutes.

---

## Accessing the App

Once deployed:

**Android (Chrome)**
1. Open your Render URL in Chrome
2. Menu (three dots) → "Install app" or "Add to Home Screen"
3. App icon appears on home screen — no browser bar

**iOS (Safari only — Chrome won't work for install)**
1. Open your Render URL in **Safari**
2. Tap Share → "Add to Home Screen"
3. App icon appears on home screen

---

## Tailscale Access

The app also supports access over Tailscale for remote development without deploying. `config.js` auto-detects the Tailscale hostname (`terra.tail8736aa.ts.net`) and routes API calls there. This requires the backend running locally with Tailscale active.

If you haven't set up Tailscale yet after the rebuild: create an account at [tailscale.com](https://tailscale.com), install on your machine, and the hostname will be available automatically.

---

## Free Tier Notes

- Render free tier **sleeps after 15 minutes of inactivity**
- First request after sleep takes ~30 seconds to wake up
- After wake-up, performance is normal
- Fine for development and personal use; upgrade to paid if you need always-on

---

## Deployment Checklist

- [ ] Code pushed to GitHub (`terra-femme/MedJournee`)
- [ ] Render service connected to GitHub repo
- [ ] All environment variables set in Render dashboard
- [ ] Build succeeds (check Render logs)
- [ ] `config.js` updated with real Render URL
- [ ] App opens at HTTPS URL
- [ ] Service worker registers (DevTools → Application → Service Workers → "activated and running")
- [ ] Install on phone tested (Android: Chrome menu → Install / iOS: Safari Share → Add to Home Screen)
