
/* Offline reading.
 *
 * The browser installs this worker the first time the page is opened from a
 * secure origin, then serves the shell and anything already viewed from cache
 * when the network is unavailable. Deploys are picked up because the page, the
 * stylesheet and the script are all revalidated or versioned.
 */

const VERSION = 'v1';
const CACHE_VERSION = 'makeup-manual-' + VERSION;
const SHELL = ['./', './index.html', './assets/book.css', './assets/book.js'];
const PICTURE = new RegExp('/assets/(?:images|pages)/');

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_VERSION);
    // cache entries individually: one missing file must not fail the install
    await Promise.all(SHELL.map(async (url) => {
      try {
        const response = await fetch(url, { cache: 'reload' });
        if (response && response.ok) await cache.put(url, response);
      } catch (error) {
        /* offline during install: the runtime handler will fill this in later */
      }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(
      names.filter((name) => name.startsWith('makeup-manual-') && name !== CACHE_VERSION)
           .map((name) => caches.delete(name))
    );
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // pictures are cached once seen, so a second visit and any later offline
  // visit are served without touching the network
  if (PICTURE.test(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request));
    return;
  }

  event.respondWith(cacheFirst(request));
});

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_VERSION);
  const hit = await cache.match(request, { ignoreSearch: false });
  if (hit) return hit;
  try {
    const response = await fetch(request);
    if (response && response.ok && response.type === 'basic') {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const fallback = await cache.match(request, { ignoreSearch: true });
    if (fallback) return fallback;
    throw error;
  }
}

async function networkFirst(request) {
  const cache = await caches.open(CACHE_VERSION);
  try {
    const response = await fetch(request);
    if (response && response.ok) cache.put(request, response.clone());
    return response;
  } catch (error) {
    return (await cache.match(request)) || (await cache.match('./index.html')) ||
           (await cache.match('./')) || Response.error();
  }
}

/* Deliberate whole-book save. The page reports progress through the worker's
   postMessage channel, so a partial save can be resumed by asking again. */
async function saveAll(client) {
  const cache = await caches.open(CACHE_VERSION);
  const response = await fetch('./index.html');
  const html = await response.text();
  const urls = Array.from(new Set(
    (html.match(new RegExp('assets/(?:images|pages)/[A-Za-z0-9_.-]+[.]jpg', 'g')) || []).map((u) => './' + u)
  ));

  let done = 0, failed = 0;
  const total = urls.length;
  const report = () => client && client.postMessage({ type: 'save-progress', done, total, failed });

  const queue = urls.slice();
  const workers = Array.from({ length: 4 }, async () => {
    while (queue.length) {
      const url = queue.shift();
      if (await cache.match(url)) { done += 1; continue; }
      try {
        const picture = await fetch(url);
        if (picture && picture.ok) await cache.put(url, picture);
        else failed += 1;
      } catch (error) {
        failed += 1;
      }
      done += 1;
      if (done % 10 === 0) report();
    }
  });
  await Promise.all(workers);
  report();
  if (client) client.postMessage({ type: 'save-done', done, total, failed });
}

self.addEventListener('message', (event) => {
  const data = event.data;
  if (data === 'clear') {
    event.waitUntil(caches.delete(CACHE_VERSION));
  } else if (data === 'save-all') {
    event.waitUntil(saveAll(event.source));
  }
});
