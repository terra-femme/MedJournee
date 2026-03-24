# MedJournee Service Worker — Caching Strategy

**File:** `static/sw.js`
**Cache name:** `medjournee-v1`

---

## Overview

The service worker intercepts every network request the app makes and decides whether to serve it from cache, fetch it fresh from the network, or both. The strategy depends on what type of content is being requested.

Medical data (API calls) is **never cached**. App shell (HTML, icons, CSS) is cached for offline use.

---

## The Four Strategies

### 1. API Routes — Network Only (no cache)

```
/transcribe, /translate, /journal, /combined, /live-session,
/realtime, /enrollment, /appointments, /talking-points, /api, /metrics
```

These routes pass straight through to the network. The service worker steps aside entirely — no caching, no interception.

**Why:** Medical transcriptions, journal entries, and appointment data must never be stored in the browser cache. Stale medical data is a patient safety issue, and cached PHI in the browser would be a HIPAA concern.

---

### 2. Static Assets — Cache First

```
/static/icons/**
manifest.json
```

Checks the cache first. If found, returns the cached version immediately. If not found, fetches from network and stores in cache for next time.

**Why:** Icons and the manifest never change between visits. Cache-first means instant load with zero network cost.

---

### 3. HTML Pages — Network First with Cache Fallback

```
Any navigation request (address bar visit, link click)
Any request with Accept: text/html
```

Always tries the network first to get the freshest version of the page. If the network fails (offline), falls back to the cached version. If no cached version exists, serves `offline.html`.

**Why:** HTML pages contain the app UI. Network-first means users always get the latest version when online, but can still access the app offline if they've visited before.

---

### 4. Everything Else — Network First with Cache Fallback

```
CSS, JS, fonts, any other static assets
```

Same as HTML pages: try network first, fall back to cache. No fallback to offline page — if unavailable, the request simply fails silently.

---

## Pre-Cached App Shell

On install, the service worker pre-caches these files so the app works immediately on first offline access (no need to have visited each page first):

```
/
/static/mobile.html
/static/appointment.html
/static/entry.html
/static/record.html
/static/enrollment.html
/static/offline.html
/static/manifest.json
/static/icons/icon-192x192.png
/static/icons/icon-512x512.png
/static/icons/apple-touch-icon.png
/static/icons/favicon.ico
/static/css/neuglass.css
```

---

## Lifecycle

**Install event:** Pre-caches all app shell URLs, then calls `skipWaiting()` to activate immediately without waiting for old tabs to close.

**Activate event:** Deletes any caches with a name other than `medjournee-v1` (cleans up old versions), then calls `clients.claim()` to take control of all open tabs immediately.

---

## How to Update the Cache (When Deploying)

When you ship new HTML, CSS, or JS, users with the old service worker installed will still see the old cached version until the SW updates.

**To force a cache bust on next visit:**

1. Change the cache name in `sw.js`:
   ```js
   const CACHE_NAME = 'medjournee-v2';  // increment the version
   ```
2. The activate event will delete `medjournee-v1` and replace it with `medjournee-v2`.
3. Users get the new version on their next visit (or immediately on next page load if `skipWaiting()` fires).

**When to bump the version:**
- Any change to HTML pages listed in `PRECACHE_URLS`
- Any change to `neuglass.css`
- Any change to icons
- Any structural change to the app shell

---

## Offline Page (`static/offline.html`)

Shown when a user tries to navigate to an HTML page that isn't cached and there's no network. It should communicate that the app is offline and guide the user to cached pages they can still access.
