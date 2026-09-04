// Service worker for the mobile PWA.
// BUILD is rewritten by build_static.py on every build, so a new deployment
// creates a fresh cache and evicts the previous one automatically.
const BUILD = "20260904161640";
const CACHE = "bio-" + BUILD;
const ASSETS = ["index.html", "app.js", "styles.css", "chart.umd.min.js",
                "manifest.webmanifest", "icon-192.png", "icon-512.png", "data.json"];

// Always fetched from the network so the daily sync is visible immediately.
const NETWORK_FIRST = ["version.json", "sync_status.json", "data.json"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE)
    .then(c => Promise.allSettled(ASSETS.map(a => c.add(a))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("message", e => {
  if (e.data === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return;          // live API: never cached
  if (e.request.method !== "GET") return;

  const file = url.pathname.split("/").pop();
  if (NETWORK_FIRST.indexOf(file) !== -1) {              // sync data: network first
    e.respondWith(fetch(e.request).then(resp => {
      const cp = resp.clone();
      caches.open(CACHE).then(c => c.put(e.request, cp));
      return resp;
    }).catch(() => caches.match(e.request)));
    return;
  }

  if (e.request.mode === "navigate") {                   // navigation: network first
    e.respondWith(fetch(e.request).catch(() => caches.match("index.html")));
    return;
  }

  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
    const cp = resp.clone();
    caches.open(CACHE).then(c => c.put(e.request, cp));
    return resp;
  }).catch(() => caches.match("index.html"))));
});
