// RoofGrid Service Worker — Offline Support & Caching
const CACHE_NAME = 'roofgrid-v37';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/privacy.html',
  '/solar_advanced.html',
  '/assets/images/roofgrid-wordmark.png',
  '/assets/images/roofgrid-app-icon.png',
  '/assets/images/roofgrid-blue-favicon-v2.svg',
  '/assets/images/apple-touch-icon.png',
  '/assets/images/feature-satellite.png',
  '/assets/images/feature-openstreetmap.png',
  '/assets/images/feature-nasa-power.png',
  '/assets/images/feature-openai.svg',
  '/assets/images/roofgrid-hero-rooftop.jpg'
];

// Install — cache core static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// Fetch — network-first for API, cache-first for static assets
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET, cross-origin, and chrome-extension requests
  if (request.method !== 'GET' || !url.protocol.startsWith('http')) return;

  // API calls — network only (don't cache dynamic data)
  if (url.pathname.startsWith('/api/')) return;

  // Page navigations — prefer the latest deployed HTML, with an offline fallback
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match('/index.html')))
    );
    return;
  }

  // Static assets & pages — stale-while-revalidate
  event.respondWith(
    caches.match(request).then((cached) => {
      const fetchPromise = fetch(request)
        .then((response) => {
          if (response && response.status === 200 && response.type === 'basic') {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => cached);

      return cached || fetchPromise;
    })
  );
});
