"""Render Stellenpilot icons: a vivid blue gradient tile with the white pilot arrow."""
# Usage: python packaging/make_icon.py stellenpilot/web
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

S = 4  # supersampling
out = Path(sys.argv[1])

def tile(size, body, radius_frac=0.225, shadow=False):
    W = size * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    b = body * S
    off = (W - b) // 2
    r = int(b * radius_frac)
    if shadow:  # soft Dock shadow like native macOS icons
        sh = Image.new("RGBA", (W, W), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([off, off + b * 0.02, off + b, off + b * 1.02], r, fill=(0, 0, 0, 90))
        img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(b * 0.025)))
    # diagonal gradient: bright electric blue top left to deep royal blue bottom right
    g = Image.new("RGBA", (b, b))
    c1, c2 = (59, 130, 255), (22, 46, 196)
    px = g.load()
    for y in range(b):
        for x in range(0, b):
            t = (x + y) / (2 * b - 2)
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)) + (255,)
    mask = Image.new("L", (b, b), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, b - 1, b - 1], r, fill=255)
    body_img = Image.new("RGBA", (b, b), (0, 0, 0, 0))
    body_img.paste(g, (0, 0), mask)
    # arrow (same shape as the old icon), with a faint shadow for depth
    pts = [(0.5, 0.14), (0.81, 0.82), (0.5, 0.675), (0.19, 0.82)]
    poly = [(off + x * b, off + y * b) for x, y in pts]
    arrow_sh = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(arrow_sh).polygon([(x, y + b * 0.018) for x, y in poly], fill=(8, 20, 90, 110))
    arrow_sh = arrow_sh.filter(ImageFilter.GaussianBlur(b * 0.018))
    img.paste(body_img, (off, off), body_img)
    img = Image.alpha_composite(img, arrow_sh)
    ImageDraw.Draw(img).polygon(poly, fill=(255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)

out.mkdir(exist_ok=True)
full = tile(1024, 984)                 # favicon, window icon, Windows: nearly full bleed like before
full.save(out / "icon.png", optimize=True)
tile(180, 180, shadow=False).save(out / "icon-180.png", optimize=True)
full.save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
tile(1024, 824, shadow=True).save(out.parent.parent / "packaging" / "icon-mac.png", optimize=True)  # Apple's icon grid: 824 px body
