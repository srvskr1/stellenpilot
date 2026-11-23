/* Visitor counter for the live traffic view (see live/README.md).
   No cookies, nothing stored on the visitor's device, no IP address kept.
   Sends the page path, the referring site and download clicks to our Cloudflare Worker. */
(function () {
  var U = ''; // Worker URL, e.g. https://stellenpilot-live.NAME.workers.dev/hit. Empty means off.
  if (!U || !navigator.sendBeacon) return;
  var id = Math.random().toString(36).slice(2) + Date.now().toString(36);
  var send = function (beat, d) {
    navigator.sendBeacon(U, JSON.stringify({ id: id, p: location.pathname, r: document.referrer, beat: beat, d: d }));
  };
  send(0);
  setInterval(function () { if (document.visibilityState === 'visible') send(1); }, 30000);

  // Download clicks. The site's own script swaps the buttons to direct .exe/.dmg links, so the link says the platform.
  var os = function (s) {
    return /\.(exe|msi)$|win/i.test(s) ? 'Windows' : /\.dmg$|mac/i.test(s) ? 'macOS' : /\.(deb|AppImage|rpm)$|linux/i.test(s) ? 'Linux' : 'Other';
  };
  var lastPip = 0, pip = function () { if (Date.now() - lastPip > 2000) { lastPip = Date.now(); send(0, 'pip'); } }; // Copy button can also fire a copy event
  addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a,button');
    if (!a) return;
    if (a.href && /github\.com\/srvskr1\/stellenpilot\/releases/.test(a.href)) {
      var p = os(a.href);
      send(0, p === 'Other' ? os(a.dataset.dl || '') : p);
    } else if (a.id === 'copy' && /pip install/.test(a.parentElement.textContent)) pip();
  }, true);
  addEventListener('copy', function () { if (/pip install/.test(String(getSelection()))) pip(); });
})();
