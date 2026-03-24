# MedJournee PWA — Overview

**Last updated:** 2026-03-24

---

## What Is the PWA

MedJournee is deployed as a Progressive Web App (PWA). This means it can be installed on a phone or tablet like a native app — users tap "Add to Home Screen" and it opens fullscreen with no browser chrome, works offline for the app shell, and behaves like a real app.

The PWA layer is entirely frontend (HTML/JS/CSS in `static/`). The FastAPI backend serves these files and is also where all API calls go.

---

## File Map

```
static/
├── manifest.json              ← Tells the browser this is a PWA
├── sw.js                      ← Service worker (caching, offline)
├── js/
│   └── config.js              ← Auto-detects environment (local / Tailscale / Render)
├── css/
│   └── neuglass.css           ← Shared stylesheet
├── icons/
│   ├── icon-192x192.png       ← Standard icon
│   ├── icon-512x512.png       ← Standard icon (large)
│   ├── icon-maskable-192x192.png  ← Maskable (adaptive) icon for Android
│   ├── icon-maskable-512x512.png  ← Maskable icon (large)
│   ├── apple-touch-icon.png   ← iOS home screen icon
│   └── favicon.ico            ← Browser tab icon
├── mobile.html                ← Main entry / dashboard
├── record.html                ← Audio recording screen
├── entry.html                 ← Journal entry view
├── appointment.html           ← New appointment form
├── all-appointments.html      ← Appointments list
├── past-appointments.html     ← Past appointments
├── journal-entries.html       ← Journal entries list
├── enrollment.html            ← Voice enrollment
├── dictionary.html            ← Medical dictionary
├── costs.html                 ← Cost dashboard
└── offline.html               ← Shown when network is unavailable
```

---

## How the PWA Is Served

FastAPI mounts the static folder and serves specific routes:

```python
app.mount("/static", StaticFiles(directory="static"), name="static")
```

The service worker **must** be served from the root scope (`/sw.js`) to control the full app. FastAPI has a dedicated route for this:

```python
@app.get("/sw.js")
async def serve_service_worker():
    # Serves static/sw.js from / instead of /static/sw.js
```

This is important — if `sw.js` were served from `/static/sw.js`, it could only control requests under `/static/`, not the whole app.

The root `/` route serves `static/mobile.html` as the app entry point.

---

## Web App Manifest (`static/manifest.json`)

The manifest tells the browser how to present the installed app:

| Field | Value | What it does |
|---|---|---|
| `name` | MedJournee - Medical Journal | Full name shown on install prompt |
| `short_name` | MedJournee | Name on home screen icon |
| `start_url` | `/` | Opens to the dashboard when launched from home screen |
| `display` | `standalone` | Fullscreen, no browser address bar |
| `orientation` | `portrait` | Locks to portrait mode |
| `background_color` | `#1a1f3c` | Splash screen background while app loads |
| `theme_color` | `#1a1f3c` | Status bar color on Android |
| `scope` | `/` | SW controls everything under `/` |

Icons include both standard and maskable variants. Maskable icons are required for Android adaptive icons (the icon is cropped to a circle/squircle shape by the launcher).

---

## Environment Auto-Detection (`static/js/config.js`)

The frontend auto-detects which backend to talk to based on the browser's hostname:

| Hostname | API target | When used |
|---|---|---|
| `localhost` or `127.0.0.1` | `http://localhost:8000` | Local development |
| `*.tail8736aa.ts.net` | `https://terra.tail8736aa.ts.net` | Tailscale (remote dev access) |
| `*.onrender.com` | `https://medjournee-backend.onrender.com` | Production on Render |

---

## See Also

- [SERVICE_WORKER.md](SERVICE_WORKER.md) — Caching strategy details
- [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md) — How to deploy / redeploy on Render
- [../../rebuild_PWA.txt](../../rebuild_PWA.txt) — Original plain-English rebuild guide (ELI5 reference, kept in project root)
