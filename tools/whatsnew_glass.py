"""Glass look for a What's new picture: python tools/whatsnew_glass.py <flat card from Codex, highlights on black> <assets/whatsnew/VERSION.jpg>"""
import sys, numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageChops
src, dst = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB"); a = np.asarray(im).astype(float)
# the icons' colour: the most saturated bright pixels
sat = a.max(2) - a.min(2); m = sat > 80
col = a[m].mean(0) if m.any() else np.array([120, 120, 255])
W, H = im.size
# background: faded black (Sam: keep it black)
y, x = np.mgrid[0:H, 0:W]
bg = np.zeros((H, W, 3))
for cx, cy, r, k in ((0.25, 0.3, 0.55, 0.06), (0.8, 0.75, 0.5, 0.04)):
    d = np.exp(-(((x / W - cx) ** 2 + ((y / H - cy) * H / W) ** 2) / (r * r * 0.35)))
    bg += d[..., None] * col * k
bg += 10  # a faded black, only a hint of the colour
base = Image.fromarray(np.clip(bg, 0, 255).astype("uint8"))
# glass panel around the content
ys, xs = np.where(a.max(2) > 40)
pad = 48
box = (xs.min() - pad, ys.min() - pad, xs.max() + pad, ys.max() + pad)
R = 44  # corner radius
x0, y0, x1, y1 = box
mask = Image.new("L", (W, H)); ImageDraw.Draw(mask).rounded_rectangle(box, R, fill=255)
inside = np.asarray(mask).astype(float) / 255
# soft shadow under the glass
shadow = Image.new("L", (W, H)); ImageDraw.Draw(shadow).rounded_rectangle((x0, y0 + 18, x1, y1 + 18), R, fill=170)
shadow = np.asarray(shadow.filter(ImageFilter.GaussianBlur(30))).astype(float) / 255 * (1 - inside)
px = np.asarray(base).astype(float) * (1 - shadow[..., None] * 0.8)
# liquid glass: a clear body that lifts what's behind it a little, brighter towards the top
t = np.clip((y - y0) / (y1 - y0), 0, 1)
body = 14 + 18 * (1 - t) ** 1.5
px += (body * inside)[..., None]
px += inside[..., None] * col * 0.05
# distance from the edge, inside the shape, for the rim light
dist = np.asarray(mask.filter(ImageFilter.GaussianBlur(3))).astype(float) / 255
ring = np.clip(1 - np.abs(dist - 0.5) * 2, 0, 1) ** 2 * inside
# specular rim: bright at the top-left and bottom-right, faint on the other two sides, like light round the edge of glass
u = (x - x0) / (x1 - x0); v = (y - y0) / (y1 - y0)
spec = np.clip(1.15 - (u + v), 0, 1) ** 1.5 + 0.55 * np.clip((u + v) - 1.2, 0, 1) ** 1.2 + 0.18
px += (ring * spec * 210)[..., None]
# an inner glow just inside the rim
inner = np.asarray(mask.filter(ImageFilter.GaussianBlur(14))).astype(float) / 255
glow = np.clip(1 - inner, 0, 1) * inside
px += (glow * 30)[..., None] + glow[..., None] * col * 0.12
base = Image.fromarray(np.clip(px, 0, 255).astype("uint8"))
# the highlights on top (black = see-through)
out = ImageChops.lighter(base, im)
out.save(dst, quality=92)
