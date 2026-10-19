#!/usr/bin/env python3
"""Crop chosen photos to 9:16 (1080x1920) so every generated shot fills the reel frame.

    python crop_916.py photos/ 019 055 069:0.35 --out src/

`ID:cx` sets the horizontal centre of the crop (0..1, default 0.5) for photos where the dish is
off-centre. Prefer portrait source photos: a 4:3 landscape photo keeps only ~42% of its width.
Writes src/<ID>.jpg and src/strip.jpg (all crops side by side) - look at the strip before
spending money on video generation.

Why pre-crop: image-to-video models given a landscape first frame either ignore aspect_ratio
(HeyGen returned the photo's own shape) or letterbox it, and mixed shapes make a reel jump
between formats. A 9:16 first frame gives native 9:16 output on Kling and Seedance.
"""
import argparse, os
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument('photos'); ap.add_argument('ids', nargs='+'); ap.add_argument('--out', default='src')
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); done = []
for spec in a.ids:
    n, _, cx = spec.partition(':'); cx = float(cx or 0.5)
    im = Image.open(os.path.join(a.photos, f'{n}.jpg')).convert('RGB'); w, h = im.size
    cw = min(w, int(h * 9 / 16)); ch = int(cw * 16 / 9)
    x = int(max(0, min(w - cw, cx * w - cw / 2))); y = (h - ch) // 2
    im.crop((x, y, x + cw, y + ch)).resize((1080, 1920), Image.LANCZOS).save(os.path.join(a.out, f'{n}.jpg'), quality=92)
    print(f'{n}: {w}x{h} -> crop {cw}x{ch}' + ('  (small source, will look soft)' if ch < 1000 else '')); done.append(n)
strip = Image.new('RGB', (len(done) * 180, 320))
for i, n in enumerate(done):
    strip.paste(Image.open(os.path.join(a.out, f'{n}.jpg')).resize((180, 320)), (i * 180, 0))
strip.save(os.path.join(a.out, 'strip.jpg')); print(os.path.join(a.out, 'strip.jpg'))
