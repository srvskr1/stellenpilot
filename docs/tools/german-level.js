// Port of stellenpilot/text.py required_german_level(). Keep the two in sync:
// scripts/check_german_level_js.py runs the engine's test phrases through both and fails on any difference.
(function (root) {
  var LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"];
  // JS has no inline (?i:...) in all browsers yet, so case-insensitive parts are spelled out per letter.
  function ci(s) {
    var out = "";
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      if (c === "\\") { out += c + s[++i]; continue; }
      out += /[a-z]/.test(c) ? "[" + c + c.toUpperCase() + "]" : c;
    }
    return out;
  }
  var DE = new RegExp(
    "(?:" + ci("\\bdeutsch(?:kenntniss\\w*|sprach\\w*|e sprache|-)|\\bdeutsche\\w*\\s+sprach\\w*") + ")" +
    "|\\bDeutsch\\b|\\bdeutsch\\b(?=\\s*(?:und|sowie|oder|&|\\(|:|[ABC][12]))" +
    "|(?:" + ci("\\bgerman\\b(?![- ]speaking)(?!\\s+(?:company|market|customers?|clients?|office|subsidiary|team|startup|branch|university|universities|speaking countries))") + ")", "g");
  var EN = /\b(?:englisch\w*|english)\b/gi;
  var Q = [
    ["C2", "muttersprach\\w*|native"],
    ["C1", "verhandlungssicher\\w*|business[ -]fluent|sehr gute?\\w*|exzellent\\w*|excellent|very good|hervorragend\\w*"],
    ["B2", "fließend\\w*|fliessend\\w*|fluent(ly)?|(?<!sehr )gute?\\w*|(?<!very )good|solide\\w*|solid|sichere\\w*|confident"],
    ["A2", "grundkenntnisse|grundlegende\\w*|basic|basis\\w*"]
  ].map(function (q) { return [q[0], new RegExp("\\b(?:" + q[1] + ")", "gi")]; });
  var OPTIONAL = /von vorteil|wünschenswert|wuenschenswert|is a plus|\ba plus\b|nice to have|ideally|optional|\bbonus\b|an advantage|advantageous|an asset|pluspunkt|\bpreferred\b|wäre schön|waere schoen/gi;
  var CEFR = /\b([ABC][12])\b/g;
  var ABBR = /\b(mind|min|ca|bzw|ggf|inkl|evtl|bspw|sog|z\. ?b|u\. ?a|d\. ?h)\./gi;
  var JOINED = /^[\s-]*(?:kenntnisse\s*)?(?:and|und|sowie|&|as well as)\s*(?:in\s+)?$/i;
  var WINDOW = 45;

  function spans(rx, s) {
    var out = [], m; rx.lastIndex = 0;
    while ((m = rx.exec(s))) { out.push([m.index, m.index + m[0].length, m[0]]); if (!m[0].length) rx.lastIndex++; }
    return out;
  }
  function dist(a, b, sp) {
    if (!sp.length) return null;
    return Math.min.apply(null, sp.map(function (g) { return b <= g[0] ? g[0] - b : a >= g[1] ? a - g[1] : 0; }));
  }
  function coordinated(s, de, en) {
    return de.some(function (d) {
      return en.some(function (e) {
        var between = e[1] <= d[0] ? s.slice(e[1], d[0]) : d[1] <= e[0] ? s.slice(d[1], e[0]) : "";
        return between && JOINED.test(between);
      });
    });
  }
  function langMatches(s, rx, de, en, win) {
    var joined = coordinated(s, de, en);
    return spans(rx, s).filter(function (m) {
      var dd = dist(m[0], m[1], de), de2 = dist(m[0], m[1], en);
      m.d = dd;
      return dd !== null && dd <= (win || WINDOW) && (de2 === null || dd <= de2 || joined);
    });
  }

  // Returns {level, sentence, optional}: level is A1..C2 or null; optional is true when German is
  // mentioned only as nice to have (the engine treats that as no requirement).
  function check(text) {
    var best = null, where = "", optional = false;
    text = String(text || "").replace(ABBR, function (_, g) { return g.replace(/\./g, ""); });
    text.split(/(?<=[.!?\n•;])/).forEach(function (s) {
      var de = spans(DE, s);
      if (!de.length) return;
      var en = spans(EN, s);
      var codes = langMatches(s, CEFR, de, en, 30).map(function (m) { return m[2].toUpperCase(); });
      var found = codes.length ? codes.reduce(function (a, b) { return LEVELS.indexOf(b) > LEVELS.indexOf(a) ? b : a; }) : null;
      if (!found) {
        var hits = [];
        Q.forEach(function (q) {
          var ms = langMatches(s, q[1], de, en);
          if (ms.length) hits.push([Math.min.apply(null, ms.map(function (m) { return m.d; })), q[0]]);
        });
        hits.sort(function (a, b) { return a[0] - b[0] || (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0); });
        found = hits.length ? hits[0][1] : null;
      }
      var opt = langMatches(s, OPTIONAL, de, en).length > 0;
      if (opt) optional = true;
      if (found && opt) return;
      if (found && (best === null || LEVELS.indexOf(found) > LEVELS.indexOf(best))) { best = found; where = s.trim(); }
    });
    return { level: best, sentence: where, optional: optional && !best };
  }

  root.germanLevel = check;
  if (typeof module !== "undefined") module.exports = check;
})(typeof window !== "undefined" ? window : globalThis);
