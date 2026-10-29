# Records docs/demo.gif from `stellenpilot demo` data (fictional only).
# Usage: stellenpilot demo && stellenpilot serve --no-browser, then python scripts/record_demo.py,
# then: ffmpeg -ss 1 -i <webm> -vf "fps=10,scale=880:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle" docs/demo.gif
# Set a name other than "Alex Example" in profile.toml first, or setup opens instead of Home.
from playwright.sync_api import sync_playwright
URL = 'http://127.0.0.1:8765/'
INIT = """
addEventListener('DOMContentLoaded',()=>{
 const s=document.createElement('style');s.textContent=`
 #cur{position:fixed;z-index:99999;width:22px;height:22px;margin:-3px 0 0 -3px;pointer-events:none;transition:transform .12s}
 #cur.dn{transform:scale(.85)}
 #cap{position:fixed;z-index:99998;left:50%;bottom:28px;transform:translate(-50%,8px);opacity:0;background:#0f172a;color:#fff;
  font:600 19px Geist,system-ui,sans-serif;padding:12px 22px;border-radius:999px;box-shadow:0 8px 30px rgba(15,23,42,.25);
  transition:opacity .35s cubic-bezier(.23,1,.32,1),transform .35s cubic-bezier(.23,1,.32,1);white-space:nowrap}
 #cap.on{opacity:1;transform:translate(-50%,0)}`;document.head.append(s);
 const c=document.createElement('div');c.id='cur';c.innerHTML='<svg viewBox="0 0 24 24" width="22" height="22"><path d="M4 2l16 10-7 1.5L9.5 21z" fill="#0f172a" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
 const p=document.createElement('div');p.id='cap';document.body.append(c,p);
 addEventListener('mousemove',e=>{c.style.left=e.clientX+'px';c.style.top=e.clientY+'px'},true);
 addEventListener('mousedown',()=>c.classList.add('dn'),true);addEventListener('mouseup',()=>c.classList.remove('dn'),true);
});
window.cap=t=>{const p=document.getElementById('cap');p.classList.remove('on');setTimeout(()=>{p.textContent=t;if(t)p.classList.add('on')},t?250:0)};
"""
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width':1280,'height':760}, record_video_dir='/tmp/vid', record_video_size={'width':1280,'height':760})
    pg = ctx.new_page(); pg.add_init_script(INIT)
    m = pg.mouse
    def cap(t): pg.evaluate('t=>cap(t)', t)
    def go(loc, steps=25):
        box = loc.bounding_box(); m.move(box['x']+box['width']/2, box['y']+box['height']/2, steps=steps)
    def click(loc): go(loc); pg.wait_for_timeout(250); loc.click(); 
    def wheel(dy, n=12):
        for _ in range(n): m.wheel(0, dy/n); pg.wait_for_timeout(30)
    vis = lambda sel: pg.locator(sel).filter(visible=True).first

    pg.goto(URL+'#home'); pg.wait_for_timeout(1200); m.move(900, 400)
    cap('Every morning: new jobs found and scored against your CV'); pg.wait_for_timeout(3000)
    click(vis('[data-page="jobs"]')); pg.wait_for_timeout(500)
    cap('Each job gets a score, the reason and your honest gaps'); pg.wait_for_timeout(2600)
    bt = pg.get_by_text('Make CV and cover letter', exact=True).filter(visible=True).first
    m.move(980, 520, steps=15); wheel(260); pg.wait_for_timeout(400)
    click(bt); pg.wait_for_timeout(600)
    cap('One click: a tailored CV and cover letter, only from your facts'); pg.wait_for_timeout(2800)
    click(pg.get_by_text('Working Student BI', exact=True).filter(visible=True).first); pg.wait_for_timeout(700)
    cap('Interview coming? Practise it with a mock interview')
    btn = pg.locator('[data-mock]').first; btn.scroll_into_view_if_needed(); pg.wait_for_timeout(600)
    click(btn); pg.wait_for_timeout(900)
    click(pg.locator('#mkAns')); pg.keyboard.type('I built a daily AWS pipeline for NYC taxi data with Python and SQL.', delay=22)
    pg.wait_for_timeout(400); click(pg.locator('[data-mkgrade]')); pg.wait_for_timeout(2400)
    click(pg.locator('[data-mkclose]')); pg.wait_for_timeout(400)
    click(vis('[data-page="apps"]')); pg.wait_for_timeout(400)
    cap('Every application on one board, Gmail moves it forward'); pg.wait_for_timeout(900)
    card = pg.get_by_text('Working Student BI', exact=True).filter(visible=True).first
    go(card); pg.wait_for_timeout(250); m.down()
    m.move(880, 275, steps=25); pg.wait_for_timeout(150); m.up(); pg.wait_for_timeout(1500)
    cap('Free, local, no account. It never applies for you.'); pg.wait_for_timeout(3000)
    ctx.close(); print(pg.video.path()); b.close()
