"""Build docs/de/index.html from docs/index.html and its DE strings.

The homepage switches language in JavaScript, which Google never sees.
This writes a real German page so German searches can find the site.
It also writes the FAQ structured data (FAQPage) in both pages from the visible FAQ.
Run after every change to docs/index.html:  python scripts/build_de_page.py
CI runs it with --check and fails if docs/de/index.html is out of date.
"""
import json
import pathlib
import re
import sys

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"
SITE = "https://stellenpilot.dev"
TITLE = "Stellenpilot: kostenloser Jobsuche-Assistent für Deutschland mit passendem Lebenslauf"
DESC = ("Stellenpilot findet jeden Morgen neue Jobs in Deutschland, bewertet sie anhand deines "
        "Lebenslaufs und schreibt Lebenslauf und Anschreiben. Kostenlos, Open Source, auf deinem Computer.")


def swap(s, old, new):
    assert s.count(old) == 1, f"expected exactly one {old[:60]!r}"
    return s.replace(old, new)


def inner_span(s, start):
    """Return (begin, end) of the inner HTML of the element whose open tag starts at `start`."""
    tag = re.match(r"<(\w+)", s[start:]).group(1)
    begin = s.index(">", start) + 1
    depth, i = 1, begin
    for m in re.compile(rf"<(/?){tag}\b[^>]*>").finditer(s, begin):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return begin, m.start()
    raise ValueError(f"unclosed <{tag}> at {start}")


FAQ_LD = '<script type="application/ld+json" id="faq-ld">'


def faq_ld(text):
    """FAQPage data for search engines and AI answers, built from the visible FAQ (key -> HTML)."""
    plain = lambda h: re.sub(r"<[^>]+>", "", h)
    qa = [{"@type": "Question", "name": plain(text[f"fq{i}"]),
           "acceptedAnswer": {"@type": "Answer", "text": plain(text[f"fa{i}"])}}
          for i in range(1, 50) if f"fq{i}" in text]
    data = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": qa}
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def with_faq_ld(page, text):
    return re.sub(re.escape(FAQ_LD) + r".*?</script>", lambda _: FAQ_LD + faq_ld(text) + "</script>", page, count=1)


def en_text(en):
    return dict(re.findall(r'data-t="(f[qa]\d+)">(.*?)</(?:h3|p)>', en))


def build(en):
    block = en[en.index("var DE={"):en.index("\n  };", en.index("var DE={"))]
    de = {k: json.loads(f'"{v}"') for k, v in re.findall(r'"?(\w+)"?:"((?:[^"\\]|\\.)*)"', block)}

    out, pos = [], 0
    for m in re.finditer(r'<\w+[^>]*\sdata-t="(\w+)"[^>]*>', en):
        if m.start() < pos:
            continue  # nested inside an element already replaced
        if m.group(1) not in de:
            continue  # no German string: keep English, as setLang does
        b, e = inner_span(en, m.start())
        out += [en[pos:b], de[m.group(1)]]
        pos = e
    s = "".join(out) + en[pos:]

    s = swap(s, '<html lang="en">', '<html lang="de">')
    s = re.sub(r"<title>.*?</title>", f"<title>{TITLE}</title>", s, count=1)
    s = re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{DESC}">', s, count=1)
    s = swap(s, f'<link rel="canonical" href="{SITE}/">', f'<link rel="canonical" href="{SITE}/de/">')
    s = swap(s, f'<meta property="og:url" content="{SITE}/">', f'<meta property="og:url" content="{SITE}/de/">')
    s = re.sub(r'(og:description" content=")[^"]*', rf"\g<1>{DESC}", s, count=1)
    s = re.sub(r'(og:title" content=")[^"]*', r"\g<1>Stellenpilot: morgens passende Jobs, mit fertigem Lebenslauf", s, count=1)
    s = with_faq_ld(s, de)
    # the page lives one folder down
    s = s.replace("url(fonts/", "url(/fonts/")
    s = re.sub(r'\b(href|src|poster)="(?!#|/|[a-z]+:)', r'\1="/', s)  # every relative link, e.g. datenschutz.html
    # language buttons: German is current, EN goes back to the English page
    s = swap(s, 'id="lang-en" aria-pressed="true"', 'id="lang-en" aria-pressed="false"')
    s = swap(s, 'id="lang-de" aria-pressed="false"', 'id="lang-de" aria-pressed="true"')
    s = swap(s, 'var lang="en",aiK=0;', 'var lang="de",aiK=0;')
    s = swap(s, 'document.getElementById("lang-de").onclick=function(){go("de","/de/")};',
             'document.getElementById("lang-de").onclick=function(){};')
    s = swap(s, AUTO_EN, 'try{if(localStorage.getItem("sp-lang")==="en")location.replace("/")}catch(e){}')
    return s


# language auto-switch on the English page (must match docs/index.html)
AUTO_EN = ('try{var saved=localStorage.getItem("sp-lang");if(saved==="de"||(!saved&&/^de/i.test(navigator.language||"")))'
           'location.replace("/de/")}catch(e){}')

if __name__ == "__main__":
    en_path = DOCS / "index.html"
    en = en_path.read_text(encoding="utf-8")
    en_new = with_faq_ld(en, en_text(en))  # keeps the English FAQ data in step with the visible FAQ
    page = build(en_new)
    target = DOCS / "de" / "index.html"
    assert 'src="/demo.mp4"' in page, "video path not rewritten for /de/"
    assert '<h1' in page and 'data-t="h1">Morgens' in page, "German h1 missing"
    if "--check" in sys.argv:
        if en_new != en or not target.exists() or target.read_text(encoding="utf-8") != page:
            sys.exit("docs/index.html FAQ data or docs/de/index.html is out of date: run python scripts/build_de_page.py")
    else:
        if en_new != en:
            en_path.write_text(en_new, encoding="utf-8")
            print("wrote", en_path)
        target.parent.mkdir(exist_ok=True)
        target.write_text(page, encoding="utf-8")
        print("wrote", target)
