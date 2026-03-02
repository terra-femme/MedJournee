const CACHE_NAME = 'medjournee-v1';

const PRECACHE_URLS = [
  '/',
  '/static/mobile.html',
  '/static/appointment.html',
  '/static/entry.html',
  '/static/record.html',
  '/static/enrollment.html',
  '/static/offline.html',
  '/static/manifest.json',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/favicon.ico',
  '/static/css/neuglass.css'
];

// Install: pre-cache app shell
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// Activate: clean up old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch: strategy depends on request type
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // API calls: network-only (never cache medical data)
  if (url.pathname.startsWith('/transcribe') ||
      url.pathname.startsWith('/translate') ||
      url.pathname.startsWith('/journal') ||
      url.pathname.startsWith('/combined') ||
      url.pathname.startsWith('/live-session') ||
      url.pathname.startsWith('/realtime') ||
      url.pathname.startsWith('/enrollment') ||
      url.pathname.startsWith('/appointments') ||
      url.pathname.startsWith('/talking-points') ||
      url.pathname.startsWith('/api') ||
      url.pathname.startsWith('/metrics')) {
    return;
  }

  // Static assets (icons, manifest): cache-first
  if (url.pathname.startsWith('/static/icons/') ||
      url.pathname.endsWith('manifest.json')) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        return cached || fetch(event.request).then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        });
      })
    );
    return;
  }

  // HTML pages (navigation): network-first, cache fallback, then offline page
  if (event.request.mode === 'navigate' ||
      (event.request.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() =>
          caches.match(event.request).then(cached =>
            cached || caches.match('/static/offline.html')
          )
        )
    );
    return;
  }

  // Everything else: network-first with cache fallback
  event.respondWith(
    fetch(event.request)
      .then(response => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
