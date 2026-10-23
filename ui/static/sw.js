/*
 * arena-cleanup service worker.
 *
 * The app shell is cached so the icon opens instantly and works on a flaky
 * connection. Nothing else is: every /api/ request goes straight to the
 * network. A cached repo status would be a lie about someone's git
 * state. If the network is gone, the shell still opens and says so.
 */

const SHELL = "arena-shell-v2";
const SHELL_FILES = [
  "/",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/apple-touch-icon.png",
  "/fonts/inter.woff2",
  "/fonts/monaspace-neon.woff2",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((cache) => cache.addAll(SHELL_FILES))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // live state: never serve a stale dashboard out of a cache
  if (url.pathname.startsWith("/api/")) return;

  // navigations: network first, so a rebuilt server is used immediately
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(SHELL).then((cache) => cache.put("/", copy));
          return response;
        })
        .catch(() => caches.match("/").then((hit) => hit || offline())),
    );
    return;
  }

  // static files: cache first, refresh in the background
  event.respondWith(
    caches.match(request).then((hit) => {
      const network = fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(SHELL).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => hit);
      return hit || network;
    }),
  );
});

function offline() {
  const html = `<!doctype html><meta charset="utf-8"><meta name="color-scheme" content="dark">
<title>arena-cleanup | Offline</title>
<style>
  html,body{height:100%;margin:0;background:#08090b;color:#c9cdd4;
    font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",system-ui,sans-serif;
    display:grid;place-items:center;text-align:center;padding:24px}
  h1{font-size:17px;margin:0 0 6px;color:#eef0f3}
  p{margin:0;color:#7c8590;max-width:34em}
</style>
<h1>The server is not reachable</h1>
<p>Every request here changes a git repo, so this app refuses to work
from a cache. Check that the container is running, then reload.</p>`;
  return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}
