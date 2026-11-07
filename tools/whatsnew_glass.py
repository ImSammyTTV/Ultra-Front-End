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
blurred = base.filter(ImageFilter.GaussianBlur(30))
mask = Image.new("L", (W, H)); ImageDraw.Draw(mask).rounded_rectangle(box, 36, fill=255)
glass = Image.blend(blurred, Image.new("RGB", (W, H), (255, 255, 255)), 0.08)
# a light sheen from the top of the panel
sheen = np.zeros((H, W)); t = np.clip((y - box[1]) / (box[3] - box[1]), 0, 1); sheen = (1 - t) ** 2 * 28
glass = Image.fromarray(np.clip(np.asarray(glass).astype(float) + sheen[..., None], 0, 255).astype("uint8"))
shadow = Image.new("L", (W, H)); ImageDraw.Draw(shadow).rounded_rectangle((box[0], box[1] + 14, box[2], box[3] + 14), 36, fill=150)
base = Image.composite(Image.new("RGB", (W, H)), base, shadow.filter(ImageFilter.GaussianBlur(24)))
base = Image.composite(glass, base, mask)
edge = Image.new("L", (W, H)); ImageDraw.Draw(edge).rounded_rectangle(box, 36, outline=255, width=2)
edge_col = Image.new("RGB", (W, H), tuple(int(c) for c in (col * 0.5 + 127)))
base = Image.composite(edge_col, base, edge.point(lambda v: v * 0.55))
# the highlights on top (black = see-through)
out = ImageChops.lighter(base, im)
out.save(dst, quality=92)
