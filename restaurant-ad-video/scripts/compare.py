#!/usr/bin/env python3
"""Side-by-side frame sheet of the same shots from two (or more) models, e.g. Kling vs Seedance.

    python compare.py --dirs clips_kling clips_seed480 --labels KLING SEED --ids 019 055 069 --times 1.5 3.5 --out compare.jpg

Rows = model x time, columns = shots. Judge motion (did the pour/squeeze/drip happen?) and
fidelity (is it still the same dish?), not sharpness, when one set is a 480p preview.
"""
import argparse, os
from PIL import Image, ImageDraw
from common import ff, font

ap = argparse.ArgumentParser()
ap.add_argument('--dirs', nargs='+', required=True); ap.add_argument('--labels', nargs='+')
ap.add_argument('--ids', nargs='+', required=True); ap.add_argument('--times', nargs='+', type=float, default=[1.5, 3.5])
ap.add_argument('--out', default='compare.jpg')
a = ap.parse_args(); labels = a.labels or [os.path.basename(d) for d in a.dirs]
w, h = 180, 320; rows = [(d, l, t) for t in a.times for d, l in zip(a.dirs, labels)]
sheet = Image.new('RGB', (len(a.ids) * w, len(rows) * h), 'white'); dr = ImageDraw.Draw(sheet)
tmp = a.out + '.frame.jpg'
for r, (d, l, t) in enumerate(rows):
    for c, n in enumerate(a.ids):
        p = os.path.join(d, f'{n}.mp4')
        if not os.path.exists(p):
            continue
        ff('-ss', t, '-i', p, '-frames:v', 1, '-vf', f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}', tmp)
        sheet.paste(Image.open(tmp), (c * w, r * h))
        dr.rectangle([c * w, r * h, c * w + 130, r * h + 26], fill='black'); dr.text((c * w + 4, r * h + 2), f'{l} {t}s', fill='yellow', font=font('latin', 18))
os.remove(tmp); sheet.save(a.out); print(a.out)
