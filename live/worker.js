// Live traffic for stellenpilot.dev. No cookies, no IPs, no storage on the visitor's device.
// POST /hit   from the site snippet (sendBeacon, text/plain, so no CORS preflight)
// GET  /live?key=VIEW_KEY   from the viewer
// GET  /                   the viewer page itself (same origin, so no CORS)

import VIEWER from './viewer.html';

const SITE = 'https://stellenpilot.dev';
const HOUR = 36e5, MIN = 6e4, ACTIVE_FOR = 70e3;
const REPO = 'srvskr1/stellenpilot', PKG = 'stellenpilot';
const CLICKS = ['Windows', 'macOS', 'Linux', 'pip', 'Other'];

// Release file name -> platform, by extension.
export const platformOf = n =>
  /\.(exe|msi)$|win/i.test(n) ? 'Windows' : /\.(dmg|pkg)$|mac|darwin/i.test(n) ? 'macOS' :
  /\.(appimage|deb|rpm)$|linux/i.test(n) ? 'Linux' : /\.(whl|tar\.gz)$/i.test(n) ? 'Python package' : 'Other';

// Real download totals: GitHub release assets (all time) and PyPI (recent).
async function totals() {
  const gh = await fetch(`https://api.github.com/repos/${REPO}/releases?per_page=100`, { headers: { 'user-agent': 'stellenpilot-live' } })
    .then(r => r.ok ? r.json() : []).catch(() => []);
  const byPlatform = {};
  for (const rel of gh) for (const a of rel.assets || []) byPlatform[platformOf(a.name)] = (byPlatform[platformOf(a.name)] || 0) + a.download_count;
  const pypi = await fetch(`https://pypistats.org/api/packages/${PKG}/recent`).then(r => r.ok ? r.json() : null).catch(() => null);
  return {
    github: Object.entries(byPlatform).sort((a, b) => b[1] - a[1]),
    githubTotal: Object.values(byPlatform).reduce((a, b) => a + b, 0),
    pypi: pypi?.data || null,
  };
}

// ponytail: state lives in the Durable Object's memory, so a restart empties it.
// Fine for a live view. Persist to this.state.storage if you want history.
export class Live {
  constructor() { this.hits = []; this.tabs = new Map(); this.totals = null; this.totalsAt = 0; }

  prune(now) {
    while (this.hits.length && now - this.hits[0].t > HOUR) this.hits.shift();
    for (const [id, t] of this.tabs) if (now - t > ACTIVE_FOR) this.tabs.delete(id);
  }

  hit(b, country, now) {
    if (!b || typeof b.id !== 'string' || b.id.length > 64) return false;
    // ponytail: caps stop a spammer from eating memory, not from inflating counts. Add rate limits if that happens.
    if (this.tabs.size < 10000) this.tabs.set(b.id, now);
    if (!b.beat && this.hits.length < 20000) {
      let ref = '';
      try { const h = new URL(b.r).hostname; if (h && !h.endsWith('stellenpilot.dev')) ref = h; } catch {}
      const hit = { t: now, p: String(b.p || '/').slice(0, 120), r: ref, c: country || '' };
      if (b.d) hit.d = CLICKS.includes(b.d) ? b.d : 'Other';   // a download click, not a page view
      this.hits.push(hit);
    }
    return true;
  }

  stats(now) {
    const perMin = Array(60).fill(0), dlPerMin = Array(60).fill(0), pages = {}, refs = {}, countries = {}, clicks = {};
    const add = (o, k) => { if (k) o[k] = (o[k] || 0) + 1; };
    for (const h of this.hits) {
      const age = now - h.t;
      const m = 59 - Math.min(59, Math.floor(age / MIN));
      if (h.d) { dlPerMin[m]++; add(clicks, h.d); continue; }
      perMin[m]++;
      if (age < 30 * MIN) { add(pages, h.p); add(refs, h.r); add(countries, h.c); }
    }
    const top = o => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, 8);
    return {
      active: this.tabs.size, perMin, pages: top(pages), refs: top(refs), countries: top(countries),
      downloads: { perMin: dlPerMin, clicks: top(clicks), ...this.totals },
      recent: this.hits.slice(-25).reverse(), now,
    };
  }

  async fetch(req) {
    const now = Date.now();
    this.prune(now);
    if (req.method === 'POST') {
      const b = await req.json().catch(() => null);
      return new Response(null, { status: this.hit(b, req.headers.get('x-country'), now) ? 204 : 400 });
    }
    // ponytail: refresh every 10 min; GitHub allows 60 unauthenticated calls an hour per IP.
    if (now - this.totalsAt > 10 * MIN) { this.totalsAt = now; this.totals = await totals(); }
    return Response.json(this.stats(now));
  }
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const live = env.LIVE.get(env.LIVE.idFromName('site'));

    if (url.pathname === '/hit' && req.method === 'POST') {
      const origin = req.headers.get('origin');
      if (origin && origin !== SITE) return new Response(null, { status: 403 });
      const body = (await req.text()).slice(0, 1000);
      await live.fetch('https://do/hit', { method: 'POST', body, headers: { 'x-country': req.cf?.country || '' } });
      return new Response(null, { status: 204, headers: { 'access-control-allow-origin': SITE } });
    }

    if (url.pathname === '/live' && req.method === 'GET') {
      const cors = { 'cache-control': 'no-store' };
      if (!env.VIEW_KEY || url.searchParams.get('key') !== env.VIEW_KEY) return new Response('no', { status: 401, headers: cors });
      const r = await live.fetch('https://do/live');
      return new Response(r.body, { headers: { ...cors, 'content-type': 'application/json' } });
    }

    if (url.pathname === '/') return new Response(VIEWER, { headers: { 'content-type': 'text/html; charset=utf-8' } });
    return new Response('not found', { status: 404 });
  },
};
