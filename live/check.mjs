import assert from 'node:assert';
import { readFileSync } from 'node:fs';
// worker.js imports viewer.html (wrangler bundles it as text); strip that line for plain node
const src = readFileSync(new URL('./worker.js', import.meta.url), 'utf8').replace(/^import VIEWER.*$/m, 'const VIEWER = "";');
const { Live } = await import('data:text/javascript,' + encodeURIComponent(src));

const d = new Live(), now = Date.now();
assert(!d.hit(null, 'DE', now));
d.hit({ id: 'b', p: '/blog/x.html', r: 'https://stellenpilot.dev/' }, 'NL', now - 2 * 6e4);
assert(d.hit({ id: 'a', p: '/', r: 'https://news.ycombinator.com/item?id=1' }, 'DE', now));
d.hit({ id: 'a', beat: 1 }, 'DE', now);                       // heartbeat: no new hit
d.hits.unshift({ t: now - 2 * 36e5, p: '/old', r: '', c: '' }); // older than an hour
d.tabs.set('gone', now - 5 * 6e4);                             // stale tab

d.prune(now);
const s = d.stats(now);
assert.equal(s.active, 1);                                   // b seen 2 min ago, gone
assert.equal(d.hits.length, 2);
assert.equal(s.perMin[59], 1);
assert.equal(s.perMin[57], 1);
assert.deepEqual(s.refs, [['news.ycombinator.com', 1]]);       // own domain dropped
assert.equal(s.recent[0].p, '/');
console.log('ok');

// downloads
const { platformOf } = await import('data:text/javascript,' + encodeURIComponent(src));
assert.equal(platformOf('Stellenpilot-Setup-0.14.1.exe'), 'Windows');
assert.equal(platformOf('Stellenpilot-0.14.1-mac.dmg'), 'macOS');
assert.equal(platformOf('stellenpilot-0.14.1.AppImage'), 'Linux');
assert.equal(platformOf('stellenpilot-0.14.1-py3-none-any.whl'), 'Python package');
const e = new Live();
e.hit({ id: 'x', p: '/' }, 'DE', now);
e.hit({ id: 'x', p: '/', d: 'Windows' }, 'DE', now);
e.hit({ id: 'x', p: '/', d: 'evil<script>' }, 'DE', now);
const t = e.stats(now);
assert.equal(t.perMin[59], 1);                                 // clicks are not page views
assert.equal(t.downloads.perMin[59], 2);
assert.deepEqual(t.downloads.clicks.map(c => c[0]).sort(), ['Other', 'Windows']);
console.log('downloads ok');
