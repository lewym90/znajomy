const VER = "znajomy-v1";
const SHELL = ["./", "index.html", "style.css", "app.js", "config.js", "manifest.webmanifest", "icon-192.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VER).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VER).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// sieć najpierw (żeby nie utknąć na starej wersji), pamięć podręczna jako zapas; API nigdy z cache
self.addEventListener("fetch", e => {
  const r = e.request;
  if (r.method !== "GET" || r.url.includes("/api/")) return;
  e.respondWith(fetch(r).then(res => {
    const copy = res.clone();
    caches.open(VER).then(c => c.put(r, copy)).catch(() => {});
    return res;
  }).catch(() => caches.match(r)));
});

self.addEventListener("push", e => {
  let d = {title: "Znajomy", body: ""};
  try { d = e.data.json(); } catch (_) {}
  e.waitUntil(self.registration.showNotification(d.title || "Znajomy", {
    body: d.body || "", icon: "icon-192.png", tag: "znajomy", renotify: true
  }));
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({type: "window", includeUncontrolled: true}).then(cs => {
    for (const c of cs) if ("focus" in c) return c.focus();
    return self.clients.openWindow("./");
  }));
});
