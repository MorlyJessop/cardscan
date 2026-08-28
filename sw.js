/* cardscan service worker: the app, the vision library and the databases work with no signal.
   index.html is fetched from the network first (so updates arrive), everything else is served from the cache once seen. */
const CACHE = "cardscan-v1";
const PRECACHE = ["./", "./index.html"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)).catch(() => {})); self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE && k !== "cardscan-db").map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (url.hostname.endsWith("anthropic.com") || url.hostname.endsWith("scryfall.com") || url.hostname.endsWith("scryfall.io")) return;   // live data: never cached here
  if (url.pathname.endsWith(".gz")) return;                                            // the app caches its databases itself (Cache API), so "Update database" always gets a fresh copy
  if (e.request.cache === "reload" || e.request.cache === "no-store") return;          // explicit refreshes bypass this cache
  const isPage = url.origin === location.origin && (url.pathname.endsWith("/") || url.pathname.endsWith("index.html"));
  if (isPage) {                                     // network first, cached copy when offline
    e.respondWith(fetch(e.request).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r; }).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(r => {   // cache first: opencv.js, .gz files, CDN libraries, card images
    if (r.ok && (url.origin === location.origin || /cdnjs|jsdelivr|opencv\.org/.test(url.hostname))) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); }
    return r;
  })));
});
